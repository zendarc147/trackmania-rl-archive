"""J6 diagnostic (not a pilot): frozen policy + scripted overrides on the final ramp.

Inside the progress window [p0, p1) the policy's action is overridden: forced full gas
without brake (--gas), and/or steering clipped to |steer| <= clip. Measures the speed and
lateral offset at take-off, the splits and the finish. Answers: which part of the policy's
behaviour on the ramp (pedals or steering) costs the take-off speed?

  uv run python scripts/j6_ramp_probe.py --run runs/j4/j6-v11-obs3-lap --checkpoint 04849183 \
      --p0 0.70 --p1 0.78
"""
from __future__ import annotations

import argparse
import dataclasses
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


def run_episode(env, model, codec, p0, p1, gas, clip):
    obs, _ = env.reset()
    marks, takeoff, progress, tail = {}, None, 0.0, []
    for _ in range(2000):
        act, _ = model.predict(np.asarray(obs, np.float32), deterministic=True)
        action = codec.decode(act)
        if p0 <= progress < p1:
            if gas:
                action = dataclasses.replace(action, accelerate=True, brake=False)
            if clip is not None:
                action = dataclasses.replace(action, steer=float(max(-clip, min(clip, action.steer))))
        t = env.step(action)
        if not t.valid:
            return {"status": "invalid", "error": t.info.get("error")}
        progress = t.info.get("progress") or 0.0
        st = env.last_state
        if takeoff is None and progress > 0.76 and not any(st.get("wheel_contact") or [True]):
            takeoff = {"progress": round(progress, 4), "race_ms": t.race_ms,
                       "display_speed": st.get("display_speed"),
                       "lateral_m": round(t.info.get("lateral_m") or 0.0, 2)}
        if progress > 0.76:
            tail.append([t.race_ms, round(progress, 4), st.get("display_speed"),
                         "".join("1" if w else "0" for w in st.get("wheel_contact") or []),
                         round(t.info.get("vertical_m") or 0.0, 2), round(t.info.get("lateral_m") or 0.0, 2),
                         round(action.steer, 2), int(action.accelerate), int(action.brake)])
        for m in (0.70, 0.775, 0.92):
            if progress >= m and m not in marks:
                marks[m] = t.race_ms
        obs = t.next_obs
        if t.done:
            break
    return {"status": t.status, "race_ms": t.race_ms, "marks": marks, "takeoff": takeoff, "tail": tail}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--speed", type=float, default=10.0)
    ap.add_argument("--p0", type=float, default=0.70)
    ap.add_argument("--p1", type=float, default=0.78)
    ap.add_argument("--clips", default="0.6,0.4,0.2")
    ap.add_argument("--only-base", action="store_true", help="only the policy and the forced-gas runs")
    args = ap.parse_args()
    run_dir = resolve(args.run)
    cfg = json.loads((run_dir / "config.json").read_text())["config"]
    model, ts = load_policy(run_dir / "checkpoints" / args.checkpoint)
    codec = make_codec(ts["action_codec"]["name"], ts["action_codec"]["ticks"])
    clips = [float(c) for c in args.clips.split(",") if c]
    grid = [(False, None), (True, None)] + [(g, c) for c in clips for g in (False, True)]
    if args.only_base:
        grid = grid[:2]
    out = ROOT / "runs" / "j6" / "ramp_probe" / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    with controller_lock("j6_ramp_probe", args):
        handle = game_env_factory(cfg, out, speed=args.speed, sync=True)(990001)
        try:
            with open(out / "probe.jsonl", "w") as f:
                for gas, clip in grid:
                    rec = {"checkpoint": args.checkpoint, "p0": args.p0, "p1": args.p1, "gas": gas,
                           "clip": clip, **run_episode(handle.env, model, codec, args.p0, args.p1,
                                                       gas, clip)}
                    f.write(json.dumps(rec) + "\n")
                    f.flush()
                    print(json.dumps({k: v for k, v in rec.items() if k != "tail"}), flush=True)
        finally:
            handle.close()
    print(f"artifacts: {out}")


if __name__ == "__main__":
    main()
