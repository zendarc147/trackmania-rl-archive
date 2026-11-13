"""Smoke test of `tm.py dashboard`: start TensorBoard for a few seconds and list its scalars.

Usage: uv run python scripts/j4_dashboard_smoke.py [--logdir runs/j4] [--port 6007]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]


def get(url):
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--logdir", default="runs/j4")
    ap.add_argument("--port", type=int, default=6007)
    a = ap.parse_args()
    p = subprocess.Popen([sys.executable, str(ROOT / "scripts" / "tm.py"), "dashboard",
                          "--logdir", a.logdir, "--port", str(a.port)], cwd=ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f"http://127.0.0.1:{a.port}"
    try:
        tags = None
        for _ in range(60):
            time.sleep(0.5)
            try:
                tags = get(base + "/data/plugin/scalars/tags")
                if tags:
                    break
            except OSError:
                continue
        if not tags:
            print("dashboard did not answer or has no scalars")
            return 1
        out = {run: sorted(t) for run, t in tags.items()}
        print(json.dumps({"url": base, "runs": len(out), "scalars": out}, indent=1))
        return 0
    finally:
        p.terminate()
        p.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
