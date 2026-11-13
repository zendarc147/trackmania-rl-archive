"""Reference line of a map: validation of a recorded run, raw and prepared versions.

Generic: every map-specific value (UID, checkpoint count, paths) comes from a map
profile in configs/maps/. Standard library only.
"""
from __future__ import annotations

import hashlib
import json
import math
import pathlib

from . import vec

RAW_SCHEMA = "trackmania_rl.reference.raw/1"
PREPARED_SCHEMA = "trackmania_rl.reference.prepared/1"
PREPARATION_DEFAULTS = {"dedup_min_step_m": 0.05, "spacing_m": 1.0, "smoothing": "none"}


def load_map_profile(path) -> dict:
    profile = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    for key in ("name", "uid", "checkpoint_count"):
        if key not in profile:
            raise ValueError(f"map profile {path}: missing {key}")
    return profile


def canonical_hash(obj) -> str:
    data = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------- recording

def split_attempts(messages: list[dict]) -> list[list[dict]]:
    """Split a passive stream into attempts; a new attempt starts when race time goes back."""
    attempts: list[list[dict]] = []
    current: list[dict] = []
    last_race = None
    for m in messages:
        if m.get("kind") == "state":
            race = m["race_ms"]
            if last_race is not None and race < last_race:
                attempts.append(current)
                current = []
            last_race = race
        if m.get("kind") in ("state", "event"):
            current.append(m)
    if current:
        attempts.append(current)
    return [a for a in attempts if any(m.get("kind") == "state" for m in a)]


def validate_run(messages: list[dict], profile: dict, *, tick_ms: int = 10,
                 max_jump_slack_m: float = 1.0) -> dict:
    """Check that one attempt is a complete, respawn-free run from the normal start.

    The finish must be confirmed by the game (finish event and RaceFinished), with the
    profile's checkpoint count reached one by one. Returns a report; valid only if no problem.
    """
    states = [m for m in messages if m.get("kind") == "state"]
    events = [m for m in messages if m.get("kind") == "event"]
    problems: list[str] = []
    report: dict = {"states": len(states), "problems": problems}
    if not states:
        problems.append("no state")
        report["valid"] = False
        return report
    uids = {s.get("map_uid") for s in states}
    if uids != {profile["uid"]}:
        problems.append(f"map uid mismatch: {sorted(map(str, uids))}")
    if not any(s["race_ms"] < 0 for s in states):
        problems.append("no countdown seen: not a normal start")
    race = [s for s in states if s["race_ms"] >= 0]
    # Race time freezes at the finish time while ticks go on: stop at the first finished state.
    first_fin = next((i for i, s in enumerate(race) if s.get("finished")), None)
    if first_fin is not None:
        race = race[: first_fin + 1]
    if not race or race[0]["race_ms"] != 0:
        problems.append("first race state is not race_ms == 0")
    gaps = sorted({b["race_ms"] - a["race_ms"] for a, b in zip(race[:-1], race[1:-1])})
    report["race_ms_steps"] = gaps
    if any(g != tick_ms for g in gaps):
        problems.append(f"race time not contiguous at {tick_ms} ms: steps {gaps}")
    if len(race) > 1 and not 0 <= race[-1]["race_ms"] - race[-2]["race_ms"] <= tick_ms:
        problems.append("last race step out of range")
    jumps = 0
    for a, b in zip(race, race[1:]):
        dt = (b["tick_ms"] - a["tick_ms"]) / 1000.0
        speed = max(vec.norm(a["velocity"]), vec.norm(b["velocity"]))
        if vec.norm(vec.sub(b["position"], a["position"])) > speed * dt * 1.5 + max_jump_slack_m:
            jumps += 1
    report["position_jumps"] = jumps
    if jumps:
        problems.append(f"{jumps} position jump(s): respawn or teleport")
    counts = [s["checkpoints"] for s in race]
    steps = sorted({b - a for a, b in zip(counts, counts[1:])})
    if any(d not in (0, 1) for d in steps):
        problems.append(f"checkpoint count not increasing by one: steps {steps}")
    target = profile["checkpoint_count"]
    cp_events = {e.get("current"): e for e in events if e.get("event") == "checkpoint"}
    crossings = []
    for k in range(1, target + 1):
        # Crossing sample: the game's callback time when available (the stream state at that
        # race time still shows the previous count), else the first state with the new count.
        ev = cp_events.get(k)
        if ev is not None:
            idx = next((i for i, s in enumerate(race) if s["race_ms"] >= ev["race_ms"]), None)
        else:
            idx = next((i for i, s in enumerate(race) if s["checkpoints"] >= k), None)
        if idx is None:
            problems.append(f"checkpoint {k}/{target} never reached")
            break
        crossings.append({"checkpoint": k, "state_index": idx, "race_ms": race[idx]["race_ms"],
                          "position": race[idx]["position"],
                          "source": "callback" if ev is not None else "state_count"})
    report["checkpoints"] = crossings
    finish_events = [e for e in events if e.get("event") == "finish"]
    final_cp = [e for e in events if e.get("event") == "checkpoint"
                and e.get("current") == target and e.get("target") == target]
    finished_states = [s for s in race if s.get("finished")]
    # Game confirmation = RaceFinished in the state stream AND the game's checkpoint callback
    # reaching the target. The bridge's own "finish" event is optional (sent once per R).
    if not finished_states or not (final_cp or finish_events):
        problems.append("finish not confirmed by the game")
    else:
        fin = finished_states[0]
        report["race_time_ms"] = fin["race_ms"]
        report["finish_state_index"] = race.index(fin)
        report["finish_confirmation"] = {
            "race_finished_state": True,
            "checkpoint_callback": [{k: e.get(k) for k in ("current", "target", "finished", "race_ms")}
                                    for e in final_cp],
            "bridge_finish_event": [e.get("race_time_ms") for e in finish_events]}
        for e in final_cp:
            if e.get("race_ms") != fin["race_ms"]:
                problems.append("checkpoint callback time differs from finished state time")
        if fin["checkpoints"] != target:
            problems.append("finished state checkpoint count differs from profile")
    cp_targets = {e.get("target") for e in events if e.get("event") == "checkpoint"}
    if cp_targets and cp_targets != {target}:
        problems.append(f"game checkpoint target {sorted(cp_targets)} != profile {target}")
    report["valid"] = not problems
    return report


# ---------------------------------------------------------------- raw reference

def raw_reference(messages: list[dict], profile: dict, report: dict, source: dict) -> dict:
    """Ordered samples from race_ms 0 to the first finished state (inclusive)."""
    if not report.get("valid"):
        raise ValueError(f"invalid run: {report.get('problems')}")
    race = [m for m in messages if m.get("kind") == "state" and m["race_ms"] >= 0]
    race = race[: report["finish_state_index"] + 1]
    samples = []
    for s in race:
        rot = s["rotation_matrix"]   # rows; columns are car axes in world (see J2 report)
        samples.append({"race_ms": s["race_ms"], "tick_ms": s["tick_ms"],
                        "position": s["position"],
                        "up": [rot[0][1], rot[1][1], rot[2][1]],
                        "forward": [rot[0][2], rot[1][2], rot[2][2]],
                        "quat_wxyz": s["quat_wxyz"], "checkpoints": s["checkpoints"],
                        "finished": s["finished"]})
    body = {"schema": RAW_SCHEMA, "map": {"name": profile["name"], "uid": profile["uid"],
                                         "checkpoint_count": profile["checkpoint_count"]},
            "source": source, "race_time_ms": report["race_time_ms"],
            "checkpoints": [{"checkpoint": c["checkpoint"], "race_ms": c["race_ms"],
                             "sample_index": c["state_index"]} for c in report["checkpoints"]],
            "frames": {"position": "world, m",
                       "up/forward": "car axes y/z in world = columns 1/2 of rotation_matrix"},
            "samples": samples}
    body["sha256"] = canonical_hash({k: v for k, v in body.items() if k != "sha256"})
    return body


# ---------------------------------------------------------------- preparation

def _cumulative(points):
    s = [0.0]
    for a, b in zip(points, points[1:]):
        s.append(s[-1] + vec.norm(vec.sub(b, a)))
    return s


def _interp_at(s_list, values, target, start=0):
    """Linear interpolation of vector values at abscissa target; returns (value, index)."""
    i = start
    while i + 1 < len(s_list) - 1 and s_list[i + 1] < target:
        i += 1
    s0, s1 = s_list[i], s_list[i + 1]
    t = 0.0 if s1 <= s0 else min(1.0, max(0.0, (target - s0) / (s1 - s0)))
    return vec.lerp(values[i], values[i + 1], t), i


def prepare_reference(raw: dict, params: dict | None = None) -> dict:
    """Deduplicate, resample by distance, add cumulative length and checkpoint sectors."""
    p = dict(PREPARATION_DEFAULTS, **(params or {}))
    if p["smoothing"] != "none":
        raise ValueError("only smoothing='none' is implemented")
    samples = raw["samples"]
    cp_index = {c["sample_index"]: c["checkpoint"] for c in raw["checkpoints"]}
    kept, kept_cp = [], {}
    for i, sm in enumerate(samples):
        is_cp = i in cp_index
        if kept and not is_cp and i != len(samples) - 1 and \
                vec.norm(vec.sub(sm["position"], kept[-1]["position"])) < p["dedup_min_step_m"]:
            continue
        if kept and vec.norm(vec.sub(sm["position"], kept[-1]["position"])) == 0.0:
            if is_cp:
                kept_cp[cp_index[i]] = len(kept) - 1
            continue
        if is_cp:
            kept_cp[cp_index[i]] = len(kept)
        kept.append(sm)
    pts = [k["position"] for k in kept]
    ups = [k["up"] for k in kept]
    s_raw = _cumulative(pts)
    total_raw = s_raw[-1]
    n = max(1, int(math.floor(total_raw / p["spacing_m"])))
    grid = [total_raw * i / n for i in range(n + 1)]
    new_pts, new_ups, j = [], [], 0
    for g in grid:
        pt, j = _interp_at(s_raw, pts, g, j)
        up, _ = _interp_at(s_raw, ups, g, j)
        new_pts.append(pt)
        new_ups.append(vec.normalize(up, fallback=[0.0, 1.0, 0.0]))
    s = _cumulative(new_pts)
    # Checkpoint arc length: raw abscissa of the crossing sample mapped onto the new grid.
    bounds = [0.0]
    for c in sorted(kept_cp):
        frac = s_raw[kept_cp[c]] / total_raw * n
        i0 = min(int(frac), n - 1)
        bounds.append(s[i0] + (s[i0 + 1] - s[i0]) * (frac - i0))
    bounds[-1] = s[-1]   # the last checkpoint is the finish, at the end of the line
    # Deviation raw vs prepared (max distance from raw kept points to the new polyline).
    dev = _max_deviation(pts, new_pts)
    body = {"schema": PREPARED_SCHEMA, "map": raw["map"], "raw_sha256": raw["sha256"],
            "params": p, "length_m": s[-1], "raw_length_m": total_raw,
            "sector_bounds_m": bounds, "raw_points_kept": len(pts),
            "raw_points_total": len(samples), "max_raw_to_prepared_m": dev,
            "points": new_pts, "ups": new_ups, "s": s}
    body["sha256"] = canonical_hash({k: v for k, v in body.items() if k != "sha256"})
    return body


def _max_deviation(raw_pts, new_pts) -> float:
    worst, j = 0.0, 0
    for p in raw_pts:
        best = math.inf
        lo, hi = max(0, j - 50), min(len(new_pts) - 1, j + 50)
        for k in range(lo, hi):
            d = vec.point_segment_distance(p, new_pts[k], new_pts[k + 1])
            if d < best:
                best, bj = d, k
        j = bj
        worst = max(worst, best)
    return worst


def save_json(obj, path) -> None:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, separators=(",", ":")), encoding="utf-8")


def load_prepared(path) -> dict:
    body = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if body.get("schema") != PREPARED_SCHEMA:
        raise ValueError("unsupported prepared reference schema")
    if canonical_hash({k: v for k, v in body.items() if k != "sha256"}) != body.get("sha256"):
        raise ValueError("prepared reference hash mismatch")
    return body
