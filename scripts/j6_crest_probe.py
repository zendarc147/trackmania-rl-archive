"""J6 diagnostic (not a pilot): frozen policy + a scripted maneuver at the first crest.

The maneuver is triggered by reference progress, not time: from progress p0, release the
gas for `lift` steps and optionally add `steer` for `steer_steps` steps. Measures the flight
(max vertical offset above the reference, airborne steps) and the splits at 0.25 / 0.30 / finish.
Grid search to learn whether a maneuver at the crest can produce the TMX landing.

  uv run python scripts/j6_crest_probe.py --run runs/j4/a01-v4-obs2b --checkpoint 00100000
"""
from __future__ import annotations

import argparse
import dataclasses
import itertools
import json
import pathlib
import sys
import time

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "src"))

from tm import controller_lock, game_env_factory  # noqa: E402
from trackmania_rl.actions import make_codec  # noqa: E402
from trackmania_rl.evaluation import load_policy  # noqa: E402
from trackmania_rl.runtime import resolve  # noqa: E402


def run_episode(env, model, codec, p0, lift, steer, steer_steps, brake=False):
    obs, _ = env.reset()
    marks, t, k, started = {}, None, 0, None
    vmax, air, land_speed = -1e9, 0, None
    progress = 0.0
    for _ in range(2000):
        act, _ = model.predict(np.asarray(obs, np.float32), deterministic=True)
        action = codec.decode(act)
        if p0 is not None and started is None and progress >= p0:
            started = k
        if started is not None:
            j = k - started
            if j < lift:
                action = dataclasses.replace(action, accelerate=False, brake=brake)
            if j < steer_steps:
                action = dataclasses.replace(action, steer=max(-1.0, min(1.0, steer)))
        t = env.step(action)
        k += 1
        if not t.valid:
            return {"status": "invalid", "error": t.info.get("error")}
        progress = t.info.get("progress") or 0.0
        st = env.last_state
        if 0.165 < progress < 0.245:
            vmax = max(vmax, t.info.get("vertical_m") or -1e9)
            if not any(st.get("wheel_contact") or [True]):
                air += 1
        if land_speed is None and progress > 0.2 and any(st.get("wheel_contact") or []):
            land_speed = st.get("display_speed")
        for m in (0.25, 0.3, 0.5):
            if progress >= m and m not in marks:
                marks[m] = t.race_ms
        obs = t.next_obs
        if t.done:
            break
    return {"status": t.status, "race_ms": t.race_ms, "marks": marks, "vertical_max_m": round(vmax, 2),
            "airborne_steps": air, "landing_display_speed": land_speed}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--speed", type=float, default=10.0)
    ap.add_argument("--p0", default="0.152,0.156,0.160,0.164")
    ap.add_argument("--lift", default="0,2,3,5")
    ap.add_argument("--steer", default="0,0.5,-0.5")
    ap.add_argument("--steer-steps", type=int, default=2)
    ap.add_argument("--brake", action="store_true", help="brake during the lift instead of coasting")
    args = ap.parse_args()
    run_dir = resolve(args.run)
    cfg = json.loads((run_dir / "config.json").read_text())["config"]
    model, ts = load_policy(run_dir / "checkpoints" / args.checkpoint)
    codec = make_codec(ts["action_codec"]["name"], ts["action_codec"]["ticks"])
    grid = [(None, 0, 0.0)] + [
        (p, l, s) for p, l, s in itertools.product(map(float, args.p0.split(",")),
                                                   map(int, args.lift.split(",")),
                                                   map(float, args.steer.split(",")))
        if l or s]
    out = ROOT / "runs" / "j6" / "crest_probe" / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    with controller_lock("j6_crest_probe", args):
        handle = game_env_factory(cfg, out, speed=args.speed, sync=True)(980001)
        try:
            with open(out / "probe.jsonl", "w") as f:
                for p, l, s in grid:
                    rec = {"p0": p, "lift": l, "steer": s, "steer_steps": args.steer_steps if s else 0,
                           "brake": args.brake,
                           **run_episode(handle.env, model, codec, p, l, s,
                                         args.steer_steps if s else 0, args.brake)}
                    f.write(json.dumps(rec) + "\n")
                    f.flush()
                    print(json.dumps(rec), flush=True)
        finally:
            handle.close()
    print(f"artifacts: {out}")


if __name__ == "__main__":
    main()
