"""J2 convention analysis on real recordings (no game needed once the traces exist).

Checks, on measured data:
  1. car x axis sense: centripetal acceleration while steering left/right, and wheel names;
  2. angular_velocity frame: finite difference of consecutive rotation matrices (10 ms),
     compared in the world frame and in the car frame;
  3. orientation discontinuities: yaw wrap, quaternion sign flips, matrix orthonormality;
  4. gear values including reverse;
  5. progress on the probe run (forward then reverse) against the prepared reference.
Usage:
  uv run python scripts/j2_conventions.py --human <trace.jsonl> --probe <rows.json>
      --prepared data/maps/a01/reference_prepared.json
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import pathlib
import statistics
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trackmania_rl import vec  # noqa: E402
from trackmania_rl.geometry import ProgressTracker, ReferenceLine  # noqa: E402
from trackmania_rl.reference import (load_map_profile, load_prepared, split_attempts,  # noqa: E402
                                     validate_run)


def mm(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def tr(a):
    return [list(r) for r in zip(*a)]


def vee(w):
    return [(w[2][1] - w[1][2]) / 2, (w[0][2] - w[2][0]) / 2, (w[1][0] - w[0][1]) / 2]


def det(m):
    return vec.dot(vec.column(m, 0), vec.cross(vec.column(m, 1), vec.column(m, 2)))


def omega_check(states):
    err_w, err_b, n = [], [], 0
    for a, b in zip(states, states[1:]):
        dt = (b["tick_ms"] - a["tick_ms"]) / 1000.0
        if dt != 0.01 or vec.norm(a["angular_velocity"]) < 0.3:
            continue
        ra, rb = a["rotation_matrix"], b["rotation_matrix"]
        w_world = vec.scale(vee(mm(rb, tr(ra))), 1 / dt)
        w_body = vec.scale(vee(mm(tr(ra), rb)), 1 / dt)
        om = a["angular_velocity"]
        err_w.append(vec.norm(vec.sub(w_world, om)))
        err_b.append(vec.norm(vec.sub(w_body, om)))
        n += 1
    rms = lambda v: math.sqrt(sum(x * x for x in v) / len(v))  # noqa: E731
    return {"samples": n, "rms_error_world_rad_s": rms(err_w), "rms_error_car_rad_s": rms(err_b),
            "median_error_world": statistics.median(err_w), "median_error_car": statistics.median(err_b)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("--human", required=True)
    ap.add_argument("--probe", required=True)
    ap.add_argument("--prepared", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    msgs = [json.loads(line) for line in open(ROOT / args.human, encoding="utf-8")]
    msgs = [m for m in msgs if m.get("dir") == "rx"]
    human = []
    valid_attempts = []
    for i, att in enumerate(split_attempts(msgs)):
        if validate_run(att, load_map_profile(ROOT / args.map))["valid"]:
            valid_attempts.append(i)
            human += [m for m in att if m.get("kind") == "state" and m["race_ms"] >= 0
                      and not m["finished"]]
    probe = json.loads((ROOT / args.probe).read_text())
    result: dict = {"human_trace": args.human, "valid_attempts_used": valid_attempts,
                    "probe_rows": args.probe}

    # 1. x axis: centripetal acceleration projected on car x while a steering key is held.
    acc = collections.defaultdict(list)
    for a, b in zip(human, human[1:]):
        if b["tick_ms"] - a["tick_ms"] != 10 or vec.norm(a["velocity"]) < 10:
            continue
        if not all(a["wheel_contact"]):
            continue
        key = {(1, 0): "left_key", (0, 1): "right_key"}.get(tuple(a["input_lr"]))
        if key is None:
            continue
        x = vec.column(a["rotation_matrix"], 0)
        dv = vec.scale(vec.sub(b["velocity"], a["velocity"]), 100.0)
        acc[key + "_acc_x"].append(vec.dot(dv, x))
        acc[key + "_steer"].append(a["car_inputs"][0])
        acc[key + "_omega_y"].append(a["angular_velocity"][1])
    result["x_axis"] = {k: {"n": len(v), "median": statistics.median(v),
                            "share_positive": sum(x > 0 for x in v) / len(v)}
                        for k, v in sorted(acc.items())}
    result["wheel_names_offsets"] = {"names": human[0]["wheel_names"],
                                     "offsets": human[0]["wheel_offsets"]}
    # probe: steer -1 then +1
    probe_turn = {}
    for label in ("steer_minus1_gas", "steer_plus1_gas"):
        rows = [r for r in probe if r["label"] == label][3:]
        probe_turn[label] = {
            "turning_rate_last": rows[-1]["turning_rate"],
            "omega_y_median": statistics.median(r["angular_velocity"][1] for r in rows),
            "yaw_change": rows[-1]["rotation_ypr"][0] - rows[0]["rotation_ypr"][0]}
    result["probe_turn"] = probe_turn

    # 2. angular velocity frame
    result["angular_velocity_frame"] = {"human": omega_check(human)}

    # 3. orientation (only consecutive physics steps of the same attempt)
    pairs = [(a, b) for a, b in zip(human, human[1:]) if b["tick_ms"] - a["tick_ms"] == 10]
    wrap = lambda a, b: abs(b["rotation_ypr"][0] - a["rotation_ypr"][0]) > math.pi  # noqa: E731
    qdot = lambda a, b: sum(x * y for x, y in zip(a["quat_wxyz"], b["quat_wxyz"]))  # noqa: E731
    result["orientation"] = {
        "consecutive_pairs": len(pairs),
        "det_min": min(det(s["rotation_matrix"]) for s in human),
        "det_max": max(det(s["rotation_matrix"]) for s in human),
        "yaw_wraps_over_pi": sum(1 for a, b in pairs if wrap(a, b)),
        "quat_sign_flips": sum(1 for a, b in pairs if qdot(a, b) < 0),
        "max_step_forward_vector": max(vec.norm(vec.sub(vec.column(b["rotation_matrix"], 2),
                                                        vec.column(a["rotation_matrix"], 2)))
                                       for a, b in pairs),
        "pitch_range": [min(s["rotation_ypr"][1] for s in human), max(s["rotation_ypr"][1] for s in human)],
        "roll_range": [min(s["rotation_ypr"][2] for s in human), max(s["rotation_ypr"][2] for s in human)]}

    # 4. gear
    rev = [r for r in probe if r["local_velocity"][2] < -1.0]
    result["gear"] = {
        "human_values": dict(collections.Counter(s["gear"] for s in human)),
        "human_rear_gear": dict(collections.Counter(s["rear_gear"] for s in human)),
        "probe_reverse_samples": len(rev),
        "probe_reverse_gear": dict(collections.Counter(r["gear"] for r in rev)),
        "probe_reverse_rear_gear": dict(collections.Counter(r["rear_gear"] for r in rev)),
        "probe_min_forward_speed": min(r["local_velocity"][2] for r in probe)}

    # 5. progress on the probe run (forward, then reverse)
    line = ReferenceLine(load_prepared(ROOT / args.prepared))
    tk = ProgressTracker(line)
    tk.reset()
    prog = []
    for r in probe:
        p = tk.update(r["position"], r["race_ms"], 0)
        prog.append((r["label"], r["race_ms"], p.s_m, p.lateral_m, p.vertical_m, p.relocalized))
    peak = max(prog, key=lambda x: x[2])
    result["probe_progress"] = {"peak_s_m": peak[2], "peak_race_ms": peak[1],
                                "final_s_m": prog[-1][2], "final_race_ms": prog[-1][1],
                                "relocalized": sum(x[5] for x in prog),
                                "lateral_range": [min(x[3] for x in prog), max(x[3] for x in prog)],
                                "decreased_while_reversing": prog[-1][2] < peak[2] - 5.0}
    text = json.dumps(result, indent=1)
    print(text)
    if args.out:
        pathlib.Path(ROOT / args.out).write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
