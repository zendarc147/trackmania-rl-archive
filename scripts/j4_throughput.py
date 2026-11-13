"""J4 throughput and physics-identity measurement (D22), single game instance.

Drives the SCRIPTED, NOT LEARNED controller reference_pursuit_v1 (deterministic) over full A01
runs from the normal start, in sync mode (D20), at several simulation speeds set through the
bridge (SPD, bridge >= 0.3.0). For each speed it records wall time, simulated time,
transitions per wall second, action -> next state latency, and the trajectory. Physics
identity: every speed is compared with the speed-1 run, transition by transition (position,
velocity, checkpoints, race time, reward). Transitions are integration data only
(data_kind = real_scripted_test, learning_data = false). Speed is set back to 1 at the end.

Usage (A01 open in the game, user's hands off the controls):
  uv run python scripts/j4_throughput.py --map configs/maps/a01.json --speeds 1 2 4 6 10
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trackmania_rl import reward as rw  # noqa: E402
from trackmania_rl import scripted_controllers as sc  # noqa: E402
from trackmania_rl.bridge import BridgeClient, BridgeError, jsonl_tracer  # noqa: E402
from trackmania_rl.runtime import build_env, load_map_assets  # noqa: E402

MAX_SPEED = 10.0   # GOAL J4 contract


def pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1)))]


def run_one(env, ctl, speed, bridge):
    ev = bridge.set_speed(speed)
    t_reset = time.monotonic()
    env.reset()
    reset_wall = time.monotonic() - t_reset
    rows, t0 = [], time.monotonic()
    while True:
        t = env.step(ctl.act(env))
        st = env.last_state
        rows.append({"action_id": t.action_id, "valid": t.valid, "status": t.status,
                     "race_ms": t.race_ms, "reward": t.reward,
                     "latency_ms": None if t.info.get("latency_s") is None else t.info["latency_s"] * 1000,
                     "position": st.get("position"), "velocity": st.get("velocity"),
                     "checkpoints": st.get("checkpoints"),
                     "steer": t.action.steer})
        if t.done or len(rows) > 1500:
            break
    wall = time.monotonic() - t0
    valid = [r for r in rows if r["valid"]]
    sim_s = sum((r["race_ms"] or 0) for r in rows[-1:]) / 1000.0
    lat = [r["latency_ms"] for r in valid if r["latency_ms"] is not None]
    return {"speed": speed, "speed_event": {k: ev.get(k) for k in ("requested", "speed_variable")},
            "reset_wall_s": reset_wall, "transitions": len(rows), "valid": len(valid),
            "status": rows[-1]["status"], "race_ms_end": rows[-1]["race_ms"],
            "sim_s": sim_s, "wall_s": wall,
            "transitions_per_wall_s": len(rows) / wall, "sim_s_per_wall_s": sim_s / wall,
            "latency_ms": {"median": statistics.median(lat), "p95": pct(lat, 0.95),
                           "max": max(lat)} if lat else None,
            "return": sum(r["reward"] for r in valid),   # undiscounted sum, identity check only
            "rows": rows}


def compare(ref, other):
    n = min(len(ref["rows"]), len(other["rows"]))
    dpos = dvel = 0.0
    first_diff = None
    for i in range(n):
        a, b = ref["rows"][i], other["rows"][i]
        if a["position"] is None or b["position"] is None:
            continue
        dp = math.dist(a["position"], b["position"])
        dv = math.dist(a["velocity"], b["velocity"])
        dpos, dvel = max(dpos, dp), max(dvel, dv)
        same = (a["race_ms"] == b["race_ms"] and a["checkpoints"] == b["checkpoints"]
                and a["status"] == b["status"] and dp == 0.0 and dv == 0.0)
        if not same and first_diff is None:
            first_diff = {"index": i, "race_ms": a["race_ms"], "dpos_m": dp, "dvel_mps": dv}
    return {"compared_transitions": n, "same_length": len(ref["rows"]) == len(other["rows"]),
            "same_end": (ref["status"], ref["race_ms_end"]) == (other["status"], other["race_ms_end"]),
            "max_position_diff_m": dpos, "max_velocity_diff_mps": dvel,
            "bitwise_identical": first_diff is None and len(ref["rows"]) == len(other["rows"]),
            "first_difference": first_diff}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("--speeds", type=float, nargs="+", default=[1, 2, 4, 6, 10])
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--first-episode", type=int, default=4001)
    args = ap.parse_args()
    if any(s <= 0 or s > MAX_SPEED for s in args.speeds):
        raise SystemExit(f"speeds must be in (0, {MAX_SPEED}] (GOAL J4 contract)")
    if args.speeds[0] != 1:
        args.speeds = [1.0] + [s for s in args.speeds if s != 1]
    assets = load_map_assets(args.map)
    out = ROOT / "runs" / "j4" / f"{time.strftime('%Y%m%d-%H%M%S')}-throughput"
    out.mkdir(parents=True, exist_ok=True)
    trace = jsonl_tracer(out / "trace.jsonl")
    bridge = BridgeClient(trace=trace)
    hello = bridge.connect()
    print(f"hello: bridge={hello.get('bridge_version')} map={hello.get('map_name')} "
          f"state={hello.get('game_state')} speed={hello.get('speed')}", flush=True)
    if hello.get("map_uid") != assets["profile"]["uid"] or hello.get("game_state") not in (512, 1024):
        print("A01 is not loaded: nothing sent", flush=True)
        bridge.close(release=False)
        return 2
    env = build_env(bridge, assets, first_episode=args.first_episode)
    ctl = sc.ReferencePursuit(assets["line"])
    results, t0 = [], time.monotonic()
    try:
        env.configure(1000, auto_restart=True)
        for rep in range(args.repeat):
            for s in args.speeds:
                r = run_one(env, ctl, s, bridge)
                r["repeat"] = rep
                results.append(r)
                print(json.dumps({k: r[k] for k in ("speed", "repeat", "status", "race_ms_end",
                                                     "transitions", "valid", "wall_s",
                                                     "transitions_per_wall_s", "sim_s_per_wall_s",
                                                     "latency_ms")}), flush=True)
    except BridgeError as exc:
        print(f"BRIDGE ERROR: {exc}", flush=True)
        results.append({"fatal_bridge_error": str(exc)})
    finally:
        try:
            bridge.send_line("REL")
            bridge.set_speed(1.0)
        except BridgeError:
            pass
        bridge.close()
        trace.close()
    runs = [r for r in results if "rows" in r]
    base = next((r for r in runs if r["speed"] == 1.0 and r["repeat"] == 0), None)
    identity = []
    if base:
        for r in runs:
            if r is not base:
                identity.append({"speed": r["speed"], "repeat": r["repeat"], **compare(base, r)})
    for c in identity:
        print(json.dumps(c), flush=True)
    with open(out / "transitions.jsonl", "w", encoding="utf-8") as f:
        for r in runs:
            for row in r["rows"]:
                f.write(json.dumps({"data_kind": "real_scripted_test", "learning_data": False,
                                    "controller": ctl.name, "speed": r["speed"],
                                    "repeat": r["repeat"], **row}, separators=(",", ":")) + "\n")
    (out / "summary.json").write_text(json.dumps(
        {"data_kind": "real_scripted_test", "learning_data": False, "hello": hello,
         "controller": ctl.describe(), "env": env.describe(),
         "runs": [{k: v for k, v in r.items() if k != "rows"} for r in results],
         "physics_identity_vs_speed1": identity, "wall_s_total": time.monotonic() - t0},
        indent=1, default=str))
    print(f"artifacts: {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
