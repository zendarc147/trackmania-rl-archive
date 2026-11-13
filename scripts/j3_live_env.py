"""J3 live run: short real episodes through TrackmaniaEnv, driven by SCRIPTED TEST CONTROLLERS.

The controllers (trackmania_rl.scripted_controllers) are NOT LEARNED and not policies. The
transitions written here are integration evidence only: data_kind = real_scripted_test,
learning_data = false. Sync mode only; resets by the environment (GiveUp). The user opens
A01 from the menu beforehand.

Scenarios (all from the normal start):
  pursuit     reference_pursuit_v1 until finish / abandon / time limit (map rules, D27)
  idle        idle_v1: no input, must end by the no-progress abandon rule
  truncate    full_gas_straight_v1 with a TEST-ONLY time limit override (3 s) -> truncation
  stall       client deliberately late (> plugin action timeout): transition invalid,
              inputs released by the plugin, then a reset recovers
  disconnect  socket closed mid-hold without REL; reconnect and check inputs are released

Usage:
  uv run python scripts/j3_live_env.py --map configs/maps/a01.json pursuit idle truncate stall disconnect
"""
from __future__ import annotations

import argparse
import json
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trackmania_rl import reward as rw  # noqa: E402
from trackmania_rl.bridge import BridgeClient, BridgeError, jsonl_tracer  # noqa: E402
from trackmania_rl.env import EpisodeRules, TrackmaniaEnv  # noqa: E402
from trackmania_rl.geometry import ProgressTracker, ReferenceLine  # noqa: E402
from trackmania_rl.observation import Encoder  # noqa: E402
from trackmania_rl.protocol import Action  # noqa: E402
from trackmania_rl.reference import load_map_profile, load_prepared  # noqa: E402
from trackmania_rl import scripted_controllers as sc  # noqa: E402

ACTION_TIMEOUT_MS = 1000


def build_env(bridge, profile, **rule_overrides):
    prepared = load_prepared(ROOT / profile["reference"]["prepared"])
    if prepared["sha256"] != profile["reference"]["prepared_content_sha256"]:
        raise SystemExit("prepared reference hash differs from the map profile")
    norm = json.loads((ROOT / profile["reference"]["normalization"]).read_text())
    line = ReferenceLine(prepared)
    env = TrackmaniaEnv(bridge, profile, Encoder(norm, profile["uid"]), ProgressTracker(line),
                        rw.RewardConfig(), EpisodeRules.from_profile(profile, **rule_overrides),
                        action_ticks=5, step_timeout_s=2.0)
    return env, line


class Recorder:
    def __init__(self, out):
        self.f = open(out / "transitions.jsonl", "a", encoding="utf-8")
        self.episodes = []

    def transition(self, scenario, controller, t):
        rec = {"data_kind": "real_scripted_test", "learning_data": False,
               "scenario": scenario, "controller": controller.name,
               "controller_learned": controller.learned, "episode": t.episode,
               "action_id": t.action_id,
               "action": [t.action.steer, t.action.accelerate, t.action.brake, t.action.ticks],
               "valid": t.valid, "status": t.status, "reward": t.reward,
               "reward_components": t.reward_components, "terminated": t.terminated,
               "truncated": t.truncated, "discount": t.discount, "dt_ms": t.dt_ms,
               "race_ms": t.race_ms, "info": t.info,
               "obs": t.obs, "next_obs": t.next_obs}
        self.f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        self.f.flush()

    def close(self):
        self.f.close()


def summarize(scenario, controller, env, trs, extra=None):
    valid = [t for t in trs if t.valid]
    comps = {k: sum(t.reward_components[k] for t in valid) for k in ("progress", "time", "finish")}
    lat = [t.info["latency_s"] * 1000 for t in valid if t.info.get("latency_s") is not None]
    last = trs[-1] if trs else None
    s = {"scenario": scenario, "controller": controller.describe(), "episode": env.episode,
         "transitions": len(trs), "valid": len(valid), "invalid": len(trs) - len(valid),
         "status": last.status if last else None,
         "terminated": last.terminated if last else None,
         "truncated": last.truncated if last else None,
         "error": last.info.get("error") if last and not last.valid else None,
         "race_ms_end": last.race_ms if last else None,
         "checkpoints_end": env.last_state.get("checkpoints") if env.last_state else None,
         "finished_flag": env.last_state.get("finished") if env.last_state else None,
         "progress_end": valid[-1].info["progress"] if valid else None,
         "progress_max": env.tracker.max_s_m / env.tracker.line.length,
         "sum_components": comps,
         "discounted_return": rw.discounted_return(
             [rw.RewardBreakdown(**t.reward_components) for t in valid]) if valid else None,
         "latency_ms": {"median": statistics.median(lat), "p95": sorted(lat)[int(0.95 * (len(lat) - 1))],
                        "max": max(lat)} if lat else None,
         "tracker": dict(env.stats)}
    if extra:
        s.update(extra)
    print(json.dumps({k: s[k] for k in ("scenario", "status", "transitions", "invalid",
                                         "race_ms_end", "checkpoints_end", "progress_max",
                                         "discounted_return", "error")}), flush=True)
    return s


def run_episode(env, controller, rec, scenario, max_steps=2000, before_step=None):
    env.reset()
    trs = []
    for i in range(max_steps):
        if before_step:
            before_step(i, env)
        t = env.step(controller.act(env))
        rec.transition(scenario, controller, t)
        trs.append(t)
        if t.done:
            break
    return trs


def game_events(bridge, episode):
    return [m for m in list(bridge.pending) if m.get("kind") == "event"
            and m.get("episode") == episode and m.get("event") in
            ("finish", "checkpoint", "released", "action_rejected")]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("scenarios", nargs="+",
                    choices=["pursuit", "idle", "truncate", "stall", "disconnect"])
    ap.add_argument("--pursuit-episodes", type=int, default=1)
    ap.add_argument("--first-episode", type=int, default=301)
    args = ap.parse_args()
    profile = load_map_profile(ROOT / args.map)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = ROOT / "runs" / "j3" / f"{stamp}-env"
    out.mkdir(parents=True, exist_ok=True)
    trace = jsonl_tracer(out / "trace.jsonl")
    bridge = BridgeClient(trace=trace)
    rec = Recorder(out)
    summaries, t0 = [], time.monotonic()
    hello = bridge.connect()
    print(f"hello: map={hello.get('map_name')} uid={hello.get('map_uid')} in_race={hello.get('in_race')}",
          flush=True)
    # 512 = in race; 1024 = end-of-race dialog of the same map (reset by GiveUp is tested there)
    if hello.get("map_uid") != profile["uid"] or hello.get("game_state") not in (512, 1024):
        print("A01 is not loaded (race or end-of-race dialog): nothing sent", flush=True)
        bridge.close(release=False)
        return 2
    episode = args.first_episode
    try:
        for scenario in args.scenarios:
            if scenario == "pursuit":
                env, line = build_env(bridge, profile)
                ctl = sc.ReferencePursuit(line)
                for _ in range(args.pursuit_episodes):
                    env.episode = episode - 1
                    env.configure(ACTION_TIMEOUT_MS)
                    trs = run_episode(env, ctl, rec, scenario, max_steps=1200)
                    ev = game_events(bridge, env.episode)
                    summaries.append(summarize(scenario, ctl, env, trs, {"game_events": ev}))
                    episode += 1
            elif scenario == "idle":
                env, _ = build_env(bridge, profile)
                env.episode = episode - 1
                env.configure(ACTION_TIMEOUT_MS)
                ctl = sc.Idle()
                trs = run_episode(env, ctl, rec, scenario)
                summaries.append(summarize(scenario, ctl, env, trs))
                episode += 1
            elif scenario == "truncate":
                env, _ = build_env(bridge, profile, time_limit_ms=3000)
                env.episode = episode - 1
                env.configure(ACTION_TIMEOUT_MS)
                ctl = sc.FullGasStraight()
                trs = run_episode(env, ctl, rec, scenario)
                summaries.append(summarize(scenario, ctl, env, trs,
                                           {"rule_override": "TEST ONLY time_limit_ms=3000"}))
                episode += 1
            elif scenario == "stall":
                env, _ = build_env(bridge, profile)
                env.episode = episode - 1
                env.configure(ACTION_TIMEOUT_MS)
                ctl = sc.FullGasStraight()

                def late(i, e):
                    if i == 20:
                        time.sleep(ACTION_TIMEOUT_MS / 1000 + 0.5)
                trs = run_episode(env, ctl, rec, scenario, max_steps=40, before_step=late)
                ev = game_events(bridge, env.episode)
                s = summarize(scenario, ctl, env, trs, {"game_events": ev})
                # recovery: a fresh episode must work after the incident
                trs2 = run_episode(env, ctl, rec, scenario + "_recovery", max_steps=10)
                s["recovery"] = {"transitions": len(trs2), "all_valid": all(t.valid for t in trs2),
                                 "episode": env.episode}
                summaries.append(s)
                episode = env.episode + 1
            elif scenario == "disconnect":
                env, _ = build_env(bridge, profile)
                env.episode = episode - 1
                env.configure(ACTION_TIMEOUT_MS)
                env.reset()
                for _ in range(20):
                    t = env.step(Action(-0.5, True, False, 5))
                    rec.transition(scenario, sc.FullGasStraight(), t)
                # send one action with 25 ticks, then drop the socket without REL mid-hold
                env.bridge.send_line(Action(-1.0, True, False, 25).encode(
                    episode=env.episode, action_id=env.action_id + 1,
                    source_seq=env.last_state["seq"]).decode().strip())
                time.sleep(0.05)
                bridge.sock.close()
                bridge.sock = None
                time.sleep(0.5)
                bridge = BridgeClient(trace=trace)
                hello2 = bridge.connect()
                bridge.configure(sync=True, timeout_ms=ACTION_TIMEOUT_MS, stream_every=1)
                seen = [m for m in bridge.drain(0.6) if m.get("kind") == "state"]
                bridge.configure(sync=True, timeout_ms=ACTION_TIMEOUT_MS, stream_every=0)
                s = {"scenario": scenario, "reconnected": hello2.get("kind") == "hello",
                     "states_after_reconnect": len(seen),
                     "commanded_after": sorted({tuple(m["commanded"]) for m in seen}),
                     "car_inputs_after": sorted({tuple(m["car_inputs"]) for m in seen}),
                     "armed_after": sorted({m["armed"] for m in seen})}
                print(json.dumps(s), flush=True)
                env2, _ = build_env(bridge, profile)
                env2.episode = env.episode
                env2.configure(ACTION_TIMEOUT_MS)
                trs2 = run_episode(env2, sc.FullGasStraight(), rec, "disconnect_recovery",
                                   max_steps=10)
                s["recovery"] = {"transitions": len(trs2), "all_valid": all(t.valid for t in trs2),
                                 "episode": env2.episode}
                summaries.append(s)
                episode = env2.episode + 1
    except BridgeError as exc:
        print(f"BRIDGE ERROR: {exc}", flush=True)
        summaries.append({"fatal_bridge_error": str(exc)})
    finally:
        try:
            bridge.send_line("REL")
            bridge.configure(sync=True, timeout_ms=ACTION_TIMEOUT_MS, stream_every=0)
        except BridgeError:
            pass
        bridge.close()
        rec.close()
        trace.close()
    env_desc = build_env(None, profile)[0].describe()
    (out / "summary.json").write_text(json.dumps(
        {"data_kind": "real_scripted_test", "learning_data": False, "hello": hello,
         "env": env_desc, "action_timeout_ms": ACTION_TIMEOUT_MS,
         "wall_s": time.monotonic() - t0, "episodes": summaries}, indent=1, default=str))
    print(f"artifacts: {out}  wall={time.monotonic() - t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
