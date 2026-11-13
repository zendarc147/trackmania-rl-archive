"""Smoke test of the Ctrl+C path of `tm.py` (SIGINT = clean stop with checkpoint).

Starts `tm.py <args>` as a child process, waits until its run reports phase "running" with at
least --after transitions, sends SIGINT once, and prints the final status. The child must
finish its current transition, save a checkpoint and exit with phase "stopped".

Usage: uv run python scripts/j4_sigint_smoke.py --run runs/j4/<id> --after 200 -- resume --run runs/j4/<id> --budget N
"""
from __future__ import annotations

import argparse
import json
import pathlib
import signal
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--after", type=int, default=200)
    ap.add_argument("--timeout", type=float, default=120)
    ap.add_argument("rest", nargs=argparse.REMAINDER)
    a = ap.parse_args()
    rest = a.rest[1:] if a.rest[:1] == ["--"] else a.rest
    run = ROOT / a.run
    start = json.loads((run / "status.json").read_text())["timesteps"] if (run / "status.json").exists() else 0
    child = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "tm.py"), *rest], cwd=ROOT)
    t0, sent = time.monotonic(), None
    while child.poll() is None and time.monotonic() - t0 < a.timeout:
        try:
            s = json.loads((run / "status.json").read_text())
        except (OSError, ValueError):
            s = {}
        if sent is None and s.get("phase") == "running" and s.get("timesteps", 0) >= start + a.after:
            child.send_signal(signal.SIGINT)
            sent = s.get("timesteps")
            print(f"SIGINT sent at status timesteps={sent}", flush=True)
        time.sleep(0.05)
    rc = child.wait(timeout=60)
    final = json.loads((run / "status.json").read_text())
    print(json.dumps({"exit_code": rc, "sigint_sent_at": sent, "phase": final["phase"],
                      "stop_reason": final["stop_reason"], "timesteps": final["timesteps"],
                      "latest_checkpoint": final["latest_checkpoint"]}, indent=1))
    return 0 if final["phase"] == "stopped" and final["stop_reason"] == "sigint" else 1


if __name__ == "__main__":
    raise SystemExit(main())
