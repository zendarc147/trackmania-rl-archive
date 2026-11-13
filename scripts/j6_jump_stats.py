"""J6 monitor (offline, reads the run's transitions.jsonl; no game needed).

Splits a run into slices of episodes and, for each slice, compares laps whose flight has no
brake (window [--flight-start, --flight-end) of reference progress) with the others: count,
finish rate, median finish time. With exploration gas bursts (v13) this shows whether the
fast-jump landings the bursts produce turn into finishes, then into faster laps.

  uv run python scripts/j6_jump_stats.py --run runs/j4/j6-v13-gasbursts
"""
import argparse
import json
import pathlib
import statistics


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument("--slices", type=int, default=8)
    ap.add_argument("--flight-start", type=float, default=0.776)
    ap.add_argument("--flight-end", type=float, default=0.92)
    a = ap.parse_args()
    eps = {}
    with open(pathlib.Path(a.run) / "transitions.jsonl") as f:
        for line in f:
            o = json.loads(line)
            e = eps.setdefault(o["episode"], {"brake": 0, "seen": False})
            if a.flight_start <= o["progress"] < a.flight_end:
                e["seen"] = True
                e["brake"] += bool(o["action"][2])
            e["status"], e["race_ms"] = o["status"], o["race_ms"]
    done = [e for _, e in sorted(eps.items()) if e["seen"] and e["status"] != "running"]
    n = len(done)
    print(f"{'slice':>5} {'laps':>5} | {'no-brake flights':>16} {'finish':>7} {'median':>7} | "
          f"{'other':>5} {'finish':>7} {'median':>7}")
    for k in range(a.slices):
        part = done[k * n // a.slices:(k + 1) * n // a.slices]
        cols = []
        for group in ([e for e in part if not e["brake"]], [e for e in part if e["brake"]]):
            fin = [e["race_ms"] / 1000 for e in group if e["status"] == "finished"]
            cols.append((len(group), f"{len(fin) / len(group):.0%}" if group else "-",
                         f"{statistics.median(fin):.2f}" if fin else "-"))
        (n1, f1, m1), (n2, f2, m2) = cols
        print(f"{k:>5} {len(part):>5} | {n1:>16} {f1:>7} {m1:>7} | {n2:>5} {f2:>7} {m2:>7}")


if __name__ == "__main__":
    main()
