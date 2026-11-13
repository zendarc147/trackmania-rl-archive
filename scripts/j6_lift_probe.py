"""J6 diagnostic (not a pilot): frozen policy + a forced gas release in a race-time window.

Tests the hypothesis from the TMX ghosts (runs/j6/replays): releasing the accelerator ~100 ms
before the first crest keeps the car on the slope instead of flying over it. Everything else
is the frozen deterministic policy. Results go to runs/j6/lift_probe/<stamp>/probe.jsonl.

  uv run python scripts/j6_lift_probe.py --run runs/j4/a01-v4-obs2b --checkpoint 00100000
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


def run_episode(env, model, codec, window, variant="base"):
    """variant: base | nobrake | ema<k> (steer = k/10 * previous + (1 - k/10) * policy) | combos with '+'."""
    obs, _ = env.reset()
    marks, t, race_ms, prev_steer = {}, None, 0, 0.0
    parts = variant.split("+")
    for _ in range(2000):
        act, _ = model.predict(np.asarray(obs, np.float32), deterministic=True)
        action = codec.decode(act)
        if "nobrake" in parts:
            action = dataclasses.replace(action, brake=False)
        if "fullgas" in parts:          # gas always on, brake kept as the policy chose
            action = dataclasses.replace(action, accelerate=True)
        for part in parts:
            if part.startswith("ema"):
                k = int(part[3:]) / 10
                action = dataclasses.replace(action, steer=k * prev_steer + (1 - k) * action.steer)
        prev_steer = action.steer
        if window and window[0] <= race_ms < window[0] + window[1]:
            action = dataclasses.replace(action, accelerate=False, brake=False)
        t = env.step(action)
        if not t.valid:
            return {"status": "invalid", "error": t.info.get("error")}
        race_ms = t.race_ms
        p = t.info.get("progress") or 0.0
        for m in (0.25, 0.5, 0.75):
            if p >= m and m not in marks:
                marks[m] = race_ms
        obs = t.next_obs
        if t.done:
            break
    return {"status": t.status, "race_ms": t.race_ms, "marks": marks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--checkpoint", required=True)
    ap.add_argument("--speed", type=float, default=10.0)
    ap.add_argument("--starts", default="7300:8400:100", help="lo:hi:step race ms")
    ap.add_argument("--durations", default="50,100,150")
    ap.add_argument("--variants", help="comma list; replaces the lift grid, e.g. base,nobrake,ema5")
    args = ap.parse_args()
    run_dir = resolve(args.run)
    cfg = json.loads((run_dir / "config.json").read_text())["config"]
    model, ts = load_policy(run_dir / "checkpoints" / args.checkpoint)
    codec = make_codec(ts["action_codec"]["name"], ts["action_codec"]["ticks"])
    lo, hi, step = (int(x) for x in args.starts.split(":"))
    windows = [None] + [(s, d) for s in range(lo, hi, step) for d in map(int, args.durations.split(","))]
    jobs = ([(None, v) for v in args.variants.split(",")] if args.variants
            else [(w, "base") for w in windows])
    out = ROOT / "runs" / "j6" / "lift_probe" / time.strftime("%Y%m%d-%H%M%S")
    out.mkdir(parents=True)
    with controller_lock("j6_lift_probe", args):
        handle = game_env_factory(cfg, out, speed=args.speed, sync=True)(970001)
        try:
            with open(out / "probe.jsonl", "w") as f:
                for w, v in jobs:
                    rec = {"window_ms": w, "variant": v, **run_episode(handle.env, model, codec, w, v)}
                    f.write(json.dumps(rec) + "\n")
                    f.flush()
                    print(json.dumps(rec), flush=True)
        finally:
            handle.close()
    print(f"artifacts: {out}")


if __name__ == "__main__":
    main()
