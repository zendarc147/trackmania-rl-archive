"""J2 convention probe: short automatic control to measure axis conventions on known cases.

Test controller with fixed open-loop actions, NOT a driving policy. Sync mode, from the
normal start (reset). Sequence: accelerate straight, full left, full right, brake to a stop,
then hold brake to test reverse. Writes runs/j2/<stamp>-conventions/{trace.jsonl,rows.json}.

Usage: uv run python scripts/j2_convention_probe.py
"""
from __future__ import annotations

import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trackmania_rl.bridge import BridgeClient, BridgeError, jsonl_tracer  # noqa: E402
from trackmania_rl.protocol import Action  # noqa: E402

SCRIPT = [  # (label, steps of 5 ticks = 50 ms, action)
    ("gas_straight", 30, Action(0.0, True, False, 5)),
    ("steer_minus1_gas", 10, Action(-1.0, True, False, 5)),
    ("steer_plus1_gas", 10, Action(1.0, True, False, 5)),
    ("brake_stop", 40, Action(0.0, False, True, 5)),
    ("brake_hold_reverse", 40, Action(0.0, False, True, 5)),
    ("release", 5, Action(0.0, False, False, 5)),
]


def main() -> int:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = ROOT / "runs" / "j2" / f"{stamp}-conventions"
    out.mkdir(parents=True, exist_ok=True)
    trace = jsonl_tracer(out / "trace.jsonl")
    c = BridgeClient(trace=trace)
    rows = []
    try:
        print(c.connect(), flush=True)
        c.configure(sync=True, timeout_ms=1000, stream_every=0)
        prev = c.reset(episode=201)
        aid = 0
        for label, n, act in SCRIPT:
            for _ in range(n):
                aid += 1
                st = c.step(201, aid, prev["seq"], act)
                rows.append({"label": label, "action": [act.steer, act.accelerate, act.brake],
                             **{k: st[k] for k in ("race_ms", "tick_ms", "position", "velocity",
                                                   "local_velocity", "rotation_matrix",
                                                   "rotation_ypr", "quat_wxyz",
                                                   "angular_velocity", "gear", "rear_gear",
                                                   "turning_rate", "car_inputs", "input_lr",
                                                   "wheel_contact", "wheel_sliding",
                                                   "display_speed")}})
                prev = st
    except BridgeError as exc:
        print(f"BRIDGE ERROR: {exc}", flush=True)
    finally:
        try:
            c.send_line("REL")
            c.configure(sync=True, timeout_ms=1000, stream_every=0)
        except BridgeError:
            pass
        c.close()
        trace.close()
    (out / "rows.json").write_text(json.dumps(rows))
    print(f"rows={len(rows)} artifacts: {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
