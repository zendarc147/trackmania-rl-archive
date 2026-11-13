"""J2 build: raw + prepared reference, control-run projection, normalization, figures.

Input: a passive human recording (runs/j2/<stamp>-human/trace.jsonl) with at least two
valid attempts: the first valid one becomes the reference, the next valid one is the
control run. Outputs:
  data/maps/<map>/reference_raw.json, reference_prepared.json, normalization_v1.json
  runs/j2/<stamp>-build/{summary.json, control_projection.json}
  docs/reports/j2/*.svg
Usage:
  uv run python scripts/j2_build_reference.py --map configs/maps/a01.json --trace <trace.jsonl>
"""
from __future__ import annotations

import argparse
import json
import math
import pathlib
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trackmania_rl import observation as obs  # noqa: E402
from trackmania_rl import reference as ref  # noqa: E402
from trackmania_rl.geometry import GEOMETRY_VERSION, ProgressTracker, ReferenceLine  # noqa: E402


def load_trace(path):
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            m = json.loads(line)
            if m.get("dir") == "rx":
                out.append(m)
    return out


def race_states(attempt, report):
    st = [m for m in attempt if m.get("kind") == "state" and m["race_ms"] >= 0]
    return st[: report["finish_state_index"] + 1]


def project_run(line, states):
    tr = ProgressTracker(line)
    tr.reset()
    rows = []
    for s in states:
        p = tr.update(s["position"], s["race_ms"], s["checkpoints"])
        rows.append({"race_ms": s["race_ms"], "checkpoints": s["checkpoints"], "s_m": p.s_m,
                     "progress": p.progress, "lateral_m": p.lateral_m,
                     "vertical_m": p.vertical_m, "distance_m": p.distance_m,
                     "sector": p.sector, "relocalized": p.relocalized, "_proj": p})
    return rows


# ---------------------------------------------------------------- SVG helpers

def svg_polylines(path, series, title, xlabel, ylabel, width=900, height=420, equal=False,
                  markers=()):
    xs = [x for _, pts, _ in series for x, _ in pts] + [m[0] for m in markers]
    ys = [y for _, pts, _ in series for _, y in pts] + [m[1] for m in markers]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    if x1 == x0:
        x1 += 1
    if y1 == y0:
        y1 += 1
    pad = 50
    sx = (width - 2 * pad) / (x1 - x0)
    sy = (height - 2 * pad) / (y1 - y0)
    if equal:
        sx = sy = min(sx, sy)

    def X(x):
        return pad + (x - x0) * sx

    def Y(y):
        return height - pad - (y - y0) * sy
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
             f'font-family="sans-serif" font-size="12">',
             '<rect width="100%" height="100%" fill="white"/>',
             f'<text x="{width / 2}" y="18" text-anchor="middle" font-size="14">{title}</text>',
             f'<text x="{width / 2}" y="{height - 8}" text-anchor="middle">{xlabel}</text>',
             f'<text x="12" y="{height / 2}" transform="rotate(-90 12 {height / 2})" '
             f'text-anchor="middle">{ylabel}</text>',
             f'<rect x="{pad}" y="{pad}" width="{width - 2 * pad}" height="{height - 2 * pad}" '
             'fill="none" stroke="#999"/>']
    for v, pos in ((x0, "start"), (x1, "end")):
        parts.append(f'<text x="{X(v)}" y="{height - pad + 14}" text-anchor="{pos}">{v:.4g}</text>')
    for v in (y0, y1):
        parts.append(f'<text x="{pad - 4}" y="{Y(v) + 4}" text-anchor="end">{v:.4g}</text>')
    if y0 < 0 < y1:
        parts.append(f'<line x1="{pad}" x2="{width - pad}" y1="{Y(0)}" y2="{Y(0)}" '
                     'stroke="#ccc" stroke-dasharray="4"/>')
    for k, (name, pts, color) in enumerate(series):
        d = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in pts)
        parts.append(f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="1.2"/>')
        parts.append(f'<text x="{pad + 8}" y="{pad + 16 + 14 * k}" fill="{color}">{name}</text>')
    for x, y, label in markers:
        parts.append(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="4" fill="black"/>'
                     f'<text x="{X(x) + 6:.1f}" y="{Y(y) - 6:.1f}">{label}</text>')
    parts.append("</svg>")
    pathlib.Path(path).write_text("\n".join(parts), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("--trace", required=True)
    ap.add_argument("--data-dir", default=None)
    args = ap.parse_args()
    profile = ref.load_map_profile(ROOT / args.map)
    slug = pathlib.Path(args.map).stem
    data_dir = ROOT / (args.data_dir or f"data/maps/{slug}")
    fig_dir = ROOT / "docs" / "reports" / "j2"
    fig_dir.mkdir(parents=True, exist_ok=True)
    out = ROOT / "runs" / "j2" / (time.strftime("%Y%m%d-%H%M%S") + "-build")
    out.mkdir(parents=True, exist_ok=True)

    trace_path = (ROOT / args.trace).resolve()
    msgs = load_trace(trace_path)
    attempts = ref.split_attempts(msgs)
    reports = [ref.validate_run(a, profile) for a in attempts]
    valid = [i for i, r in enumerate(reports) if r["valid"]]
    print("attempts:", [(i, r["valid"], r.get("race_time_ms"), r["problems"]) for i, r in enumerate(reports)])
    if len(valid) < 2:
        print("need two valid runs (reference + control)")
        return 1
    i_ref, i_ctl = valid[0], valid[1]
    source = {"kind": "real_human", "trace": str(trace_path.relative_to(ROOT)),
              "attempt_index": i_ref, "recorder": "scripts/j2_record_reference.py",
              "bridge": "TrackmaniaRLBridge 0.1.0, stream every physics step (10 ms)"}
    raw = ref.raw_reference(attempts[i_ref], profile, reports[i_ref], source)
    prepared = ref.prepare_reference(raw)
    ref.save_json(raw, data_dir / "reference_raw.json")
    ref.save_json(prepared, data_dir / "reference_prepared.json")
    prepared = ref.load_prepared(data_dir / "reference_prepared.json")   # hash check
    line = ReferenceLine(prepared)

    ref_states = race_states(attempts[i_ref], reports[i_ref])
    ctl_states = race_states(attempts[i_ctl], reports[i_ctl])
    ref_proj = project_run(line, ref_states)
    ctl_proj = project_run(line, ctl_states)

    # Normalization statistics: real human driving only (both valid runs), marked as such.
    feats = [obs.raw_features(s, r["_proj"]) for s, r in zip(ref_states, ref_proj)]
    feats += [obs.raw_features(s, r["_proj"]) for s, r in zip(ctl_states, ctl_proj)]
    norm = obs.fit_normalization(
        feats, data_kind="real_human",
        sources=[f"{source['trace']}#attempt{i_ref}", f"{source['trace']}#attempt{i_ctl}"],
        map_uid=profile["uid"], reference_sha256=prepared["sha256"])
    ref.save_json(norm, data_dir / "normalization_v1.json")
    enc = obs.Encoder(norm, profile["uid"])
    determinism = all(enc.encode(s, r["_proj"]) == enc.encode(s, r["_proj"])
                      for s, r in zip(ctl_states[::50], ctl_proj[::50]))
    enc_rows = [enc.encode(s, r["_proj"]) for s, r in zip(ctl_states, ctl_proj)]
    clipped = sum(1 for row in enc_rows for x in row if abs(x) >= obs.CLIP)

    def stats(rows, key):
        v = [r[key] for r in rows]
        return {"min": min(v), "max": max(v), "median": statistics.median(v),
                "p95_abs": sorted(abs(x) for x in v)[int(0.95 * (len(v) - 1))]}

    def monotonic_breaks(rows, tol=0.05):
        return sum(1 for a, b in zip(rows, rows[1:]) if b["s_m"] < a["s_m"] - tol)

    def cp_progress(rows, states, report):
        return [{"checkpoint": c["checkpoint"], "race_ms": c["race_ms"],
                 "s_m": rows[c["state_index"]]["s_m"]} for c in report["checkpoints"]]

    summary = {
        "trace": source["trace"], "reports": reports, "reference_attempt": i_ref,
        "control_attempt": i_ctl, "geometry_version": GEOMETRY_VERSION,
        "observation_schema": obs.SCHEMA_VERSION, "dim": obs.DIM,
        "raw": {"samples": len(raw["samples"]), "sha256": raw["sha256"],
                "race_time_ms": raw["race_time_ms"]},
        "prepared": {k: prepared[k] for k in ("params", "length_m", "raw_length_m",
                                              "sector_bounds_m", "raw_points_kept",
                                              "raw_points_total", "max_raw_to_prepared_m",
                                              "sha256")},
        "prepared_points": len(prepared["points"]),
        "normalization": {"sha256": norm["sha256"], "samples": norm["samples"],
                          "data_kind": norm["data_kind"]},
        "reference_run_projection": {k: stats(ref_proj, k) for k in ("lateral_m", "vertical_m",
                                                                     "distance_m")}
        | {"relocalized": sum(r["relocalized"] for r in ref_proj),
           "backward_steps": monotonic_breaks(ref_proj),
           "final_progress": ref_proj[-1]["progress"],
           "checkpoints": cp_progress(ref_proj, ref_states, reports[i_ref])},
        "control_run_projection": {k: stats(ctl_proj, k) for k in ("lateral_m", "vertical_m",
                                                                   "distance_m")}
        | {"relocalized": sum(r["relocalized"] for r in ctl_proj),
           "backward_steps": monotonic_breaks(ctl_proj),
           "final_progress": ctl_proj[-1]["progress"],
           "race_time_ms": reports[i_ctl]["race_time_ms"],
           "checkpoints": cp_progress(ctl_proj, ctl_states, reports[i_ctl])},
        "encoding": {"deterministic_sample": determinism, "clipped_values": clipped,
                     "values": len(enc_rows) * obs.DIM},
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    (out / "control_projection.json").write_text(json.dumps(
        [{k: v for k, v in r.items() if k != "_proj"} for r in ctl_proj]))

    # ---- figures
    rawp = [s["position"] for s in raw["samples"]]
    svg_polylines(fig_dir / "reference_top.svg",
                  [("raw (10 ms samples)", [(p[0], -p[2]) for p in rawp], "#d62728"),
                   ("prepared (1 m)", [(p[0], -p[2]) for p in prepared["points"]], "#1f77b4")],
                  f"{profile['name']}: reference, top view (looking down -y)", "x (m)", "-z (m)",
                  width=900, height=700, equal=True,
                  markers=[(c["position"][0], -c["position"][2], f"CP{c['checkpoint']}")
                           for c in reports[i_ref]["checkpoints"]]
                  + [(rawp[0][0], -rawp[0][2], "start")])
    svg_polylines(fig_dir / "reference_altitude.svg",
                  [("raw", list(zip(ref._cumulative(rawp), [p[1] for p in rawp])), "#d62728"),
                   ("prepared", list(zip(prepared["s"], [p[1] for p in prepared["points"]])),
                    "#1f77b4")],
                  "Altitude along the reference", "arc length (m)", "y (m)")
    # raw vs prepared deviation per raw point
    tr = ProgressTracker(line)
    tr.reset()
    dev = [(ref_proj[k]["s_m"], ref_proj[k]["distance_m"]) for k in range(len(ref_proj))]
    svg_polylines(fig_dir / "raw_vs_prepared_deviation.svg",
                  [("distance raw sample -> prepared line (m)", dev, "#2ca02c")],
                  "Raw reference vs prepared: projection distance", "arc length (m)", "m")
    t = [r["race_ms"] / 1000 for r in ctl_proj]
    svg_polylines(fig_dir / "control_offsets.svg",
                  [("lateral (+left)", list(zip(t, [r["lateral_m"] for r in ctl_proj])), "#1f77b4"),
                   ("vertical (+normal)", list(zip(t, [r["vertical_m"] for r in ctl_proj])),
                    "#ff7f0e")],
                  "Control run: signed offsets to the reference", "race time (s)", "m")
    svg_polylines(fig_dir / "control_progress.svg",
                  [("control run", list(zip(t, [r["progress"] for r in ctl_proj])), "#1f77b4"),
                   ("reference run", [(r["race_ms"] / 1000, r["progress"]) for r in ref_proj],
                    "#999999")],
                  "Progress vs race time", "race time (s)", "progress",
                  markers=[(c["race_ms"] / 1000, c["s_m"] / line.length, f"CP{c['checkpoint']}")
                           for c in summary["control_run_projection"]["checkpoints"]])
    print(json.dumps({k: summary[k] for k in ("raw", "prepared", "normalization", "encoding",
                                              "reference_run_projection",
                                              "control_run_projection")}, indent=1))
    print("artifacts:", out, data_dir, fig_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
