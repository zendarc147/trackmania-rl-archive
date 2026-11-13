"""J2 passive recorder: store a human A01 run streamed by the bridge at every physics step.

The client never sends an action or a reset: it only configures the stream (CFG 0 ... 1)
and listens. The human drives. The run is written to runs/j2/<stamp>/trace.jsonl, then
validated with trackmania_rl.reference.validate_run (map identity, start, continuity,
no respawn/restart, checkpoints in order, finish confirmed by the game).

Usage:
  uv run python scripts/j2_record_reference.py --map configs/maps/a01.json [--seconds 150]
Start the script with the race open, then restart the race in game (countdown) and drive.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trackmania_rl.bridge import BridgeClient, BridgeError, jsonl_tracer  # noqa: E402
from trackmania_rl.reference import load_map_profile, split_attempts, validate_run  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("--seconds", type=float, default=150.0)
    ap.add_argument("--tag", default="reference")
    ap.add_argument("--finishes", type=int, default=1, help="stop 2 s after this many finishes")
    args = ap.parse_args()
    profile = load_map_profile(ROOT / args.map)

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = ROOT / "runs" / "j2" / f"{stamp}-{args.tag}"
    out.mkdir(parents=True, exist_ok=True)
    trace = jsonl_tracer(out / "trace.jsonl")
    client = BridgeClient(trace=trace)
    hello = client.connect()
    print(f"hello: map_uid={hello.get('map_uid')} in_race={hello.get('in_race')}", flush=True)
    if hello.get("map_uid") != profile["uid"]:
        print(f"WRONG MAP: expected {profile['uid']}", flush=True)
    msgs: list[dict] = []
    try:
        client.configure(sync=False, timeout_ms=1000, stream_every=1)
        print(f"recording up to {args.seconds:.0f}s: restart the race and drive (stops 2 s after finish)",
              flush=True)
        end = time.monotonic() + args.seconds
        finish_at, finishes = None, 0
        while time.monotonic() < end:
            batch = client.drain(0.25)
            msgs.extend(batch)
            for m in batch:
                if m.get("event") == "checkpoint":
                    print(f"  checkpoint {m.get('current')}/{m.get('target')} race_ms={m.get('race_ms')}",
                          flush=True)
                if m.get("event") == "checkpoint" and m.get("current") == m.get("target"):
                    # The plugin's "finish" event fires once per R command only; passive
                    # recording relies on the game's checkpoint callback + RaceFinished.
                    finishes += 1
                    print(f"  finish #{finishes} race_ms={m.get('race_ms')} "
                          f"finished={m.get('finished')}", flush=True)
                    if finishes >= args.finishes:
                        finish_at = time.monotonic()
            if finish_at is not None and time.monotonic() - finish_at > 2.0:
                break
    except BridgeError as exc:
        print(f"BRIDGE ERROR: {exc}", flush=True)
    finally:
        try:
            client.configure(sync=True, timeout_ms=1000, stream_every=0)
        except BridgeError:
            pass
        client.close(release=False)   # passive: never send REL/inputs
        trace.close()

    attempts = split_attempts(msgs)
    reports = [validate_run(a, profile) for a in attempts]
    summary = {"stamp": stamp, "map_config": args.map, "messages": len(msgs),
               "attempts": reports}
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    for i, r in enumerate(reports):
        print(f"attempt {i}: valid={r['valid']} race_time_ms={r.get('race_time_ms')} "
              f"problems={r['problems']}", flush=True)
    print(f"artifacts: {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
