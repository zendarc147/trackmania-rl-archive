"""Summarize the transitions of one evaluation directory (decision latency, real-time lag).

Usage: uv run python scripts/j4_eval_timing.py runs/j4/<run>/evals/<eval_dir>
"""
from __future__ import annotations

import collections
import json
import pathlib
import statistics
import sys


def main() -> int:
    d = pathlib.Path(sys.argv[1])
    rows = [json.loads(line) for line in (d / "eval_transitions.jsonl").read_text().splitlines()]
    valid = [r for r in rows if r["valid"]]
    lat = sorted(r["latency_ms"] for r in valid if r["latency_ms"] is not None)
    dec = sorted(r["decision_ms"] for r in rows)
    out = {"eval_dir": str(d), "transitions": len(rows), "valid": len(valid),
           "dt_ms_counts": dict(collections.Counter(r["dt_ms"] for r in valid)),
           "decision_ms": {"median": statistics.median(dec), "p95": dec[int(0.95 * (len(dec) - 1))],
                           "max": dec[-1]} if dec else None,
           "action_to_state_ms": {"median": statistics.median(lat), "p95": lat[int(0.95 * (len(lat) - 1))],
                                  "max": lat[-1]} if lat else None,
           "errors": [r["error"] for r in rows if not r["valid"]]}
    print(json.dumps(out, indent=1))
    (d / "timing_summary.json").write_text(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
