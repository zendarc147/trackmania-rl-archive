"""Observation schema v1: raw bridge state + reference projection -> model vector.

Only the fields approved in docs/OBSERVATIONS.md are encoded. Transformations change the
number of inputs (orientation as two unit vectors) without adding physical information.
Everything else in the state (position, rpm, display speed, rear gear, inputs...) is
environment-internal or diagnostic and never reaches the vector.

Error rules: a missing, non-finite, wrongly typed or stale value raises ObservationError.
The caller must then invalidate the transition. No value is ever replaced by zero.
"""
from __future__ import annotations

import hashlib
import json
import math

from . import vec
from .geometry import Projection

SCHEMA_VERSION = "trackmania_rl.observation/1"
EPISODE_SCHEMA_VERSION = "trackmania_rl.observation/2"
LOOKAHEAD_SCHEMA_VERSION = "trackmania_rl.observation/3"
# J6 (D18 extension approved by the user on 2026-10-02): reference-line points ahead of the
# projection, as (point - car position) in the car frame divided by the lookahead distance.
LOOKAHEAD_M = (10.0, 25.0, 50.0, 100.0, 150.0, 200.0)
NORMALIZATION_SCHEMA = "trackmania_rl.normalization/1"
CLIP = 5.0

# (internal name, approved label, width, unit, frame, source, normalization method)
FIELDS = [
    ("velocity_car", "Velocity X/Y/Z", 3, "m/s", "car (x left, y up, z forward)",
     "R^T Dyna.CurrentState.LinearSpeed", "zscore"),
    ("rotation_forward", "Rotation X/Y/Z (1/2)", 3, "unit vector", "world",
     "column 2 of Dyna.CurrentState.Location.Rotation (car z in world)", "identity"),
    ("rotation_up", "Rotation X/Y/Z (2/2)", 3, "unit vector", "world",
     "column 1 of Dyna.CurrentState.Location.Rotation (car y in world)", "identity"),
    ("angular_velocity_car", "Angular Velocity X/Y/Z", 3, "rad/s", "car (x left, y up, z forward)",
     "R^T Dyna.CurrentState.AngularSpeed (world frame in the game)", "zscore"),
    ("gear", "Gear", 1, "gear index", "-", "SceneVehicleCar.CarEngine.Gear", "zscore"),
    ("turning_rate", "Turning Rate", 1, "normalized [-1, 1]", "-",
     "SceneVehicleCar.TurningRate", "identity"),
    ("centerline_lateral", "Centerline Lateral Distance", 1, "m", "reference frame, + left",
     "geometry.ProgressTracker from Location.Position", "zscore"),
    ("centerline_vertical", "Centerline Vertical Distance", 1, "m",
     "reference frame, + along local normal", "geometry.ProgressTracker", "zscore"),
    ("progress", "Progress", 1, "fraction of reference length [0, 1]", "reference",
     "geometry.ProgressTracker arc length / length", "identity"),
    ("wheel_contact", "Wheels Contact 1/2/3/4", 4, "0/1", "order FL, FR, BR, BL",
     "Wheels[i].RTState.HasGroundContact", "identity"),
    ("wheel_sliding", "Wheels Sliding 1/2/3/4", 4, "0/1", "order FL, FR, BR, BL",
     "Wheels[i].RTState.IsSliding", "identity"),
]
DIM = sum(f[2] for f in FIELDS)


def observation_contract(schema: str = SCHEMA_VERSION) -> dict:
    """v1 stays byte-compatible; v2 appends the approved abandonment state (J4-15);
    v3 appends the reference points ahead of the car (J6, D18)."""
    if schema not in (SCHEMA_VERSION, EPISODE_SCHEMA_VERSION, LOOKAHEAD_SCHEMA_VERSION):
        raise ValueError(f"unknown observation schema: {schema}")
    extra = ([] if schema == SCHEMA_VERSION else
             ["no_progress_remaining_fraction", "progress_record_gap_fraction"])
    contract = {"schema": schema, "dim": DIM + len(extra), "base_schema": SCHEMA_VERSION,
                "episode_features": extra}
    if schema == LOOKAHEAD_SCHEMA_VERSION:
        names = [f"lookahead_{d:g}m.{a}" for d in LOOKAHEAD_M for a in "xyz"]
        contract.update(dim=contract["dim"] + len(names), lookahead_features=names,
                        lookahead_m=list(LOOKAHEAD_M),
                        lookahead_frame="car (x left, y up, z forward), divided by the distance")
    return contract


def lookahead_features(line, s_m: float, state: dict) -> list[float]:
    """Reference points at s_m + d (clamped to the finish), relative to the car, car frame.

    Geometry of the course only: no time, command or demonstrated trajectory."""
    rot = _matrix(state)
    pos = _vec3(state, "position")
    out = []
    for d in LOOKAHEAD_M:
        r = vec.sub(line.point_at(min(s_m + d, line.length)), pos)
        out += [x / d for x in vec.mat_T_vec(rot, r)]
    if not all(math.isfinite(x) for x in out):
        raise ObservationError("non-finite lookahead")
    return out


def episode_features(*, race_ms: int, best_race_ms: int, no_progress_ms: int,
                     progress_s_m: float, best_s_m: float, length_m: float) -> list[float]:
    """Current abandonment timer and signed distance to its registered record.

    Called AFTER updating the record for the current state, including terminal states.
    The small negative gap before min_gain_m is exceeded is intentional, not clipped away.
    """
    if no_progress_ms <= 0 or length_m <= 0 or race_ms < best_race_ms:
        raise ObservationError("invalid episode observation context")
    values = [max(0.0, 1.0 - (race_ms - best_race_ms) / no_progress_ms),
              (best_s_m - progress_s_m) / length_m]
    if not all(math.isfinite(x) for x in values):
        raise ObservationError("non-finite episode observation context")
    return values


class ObservationError(ValueError):
    """Observation unusable: the transition that produced it must be invalidated."""


def _num(state, key):
    v = state.get(key)
    if type(v) not in (int, float) or not math.isfinite(v):
        raise ObservationError(f"missing or non-finite: {key}")
    return float(v)


def _vec3(state, key):
    v = state.get(key)
    if not isinstance(v, list) or len(v) != 3:
        raise ObservationError(f"missing or invalid vector: {key}")
    if not all(type(x) in (int, float) and math.isfinite(x) for x in v):
        raise ObservationError(f"non-finite value in {key}")
    return [float(x) for x in v]


def _matrix(state):
    m = state.get("rotation_matrix")
    if not isinstance(m, list) or len(m) != 3 or any(not isinstance(r, list) or len(r) != 3 for r in m):
        raise ObservationError("missing or invalid vector: rotation_matrix")
    if not all(type(x) in (int, float) and math.isfinite(x) for r in m for x in r):
        raise ObservationError("non-finite value in rotation_matrix")
    return m


def _bools(state, key):
    v = state.get(key)
    if not isinstance(v, list) or len(v) != 4 or any(type(x) is not bool for x in v):
        raise ObservationError(f"missing or invalid per-wheel field: {key}")
    return [1.0 if x else 0.0 for x in v]


def raw_features(state: dict, proj: Projection, *, expected_tick_ms: int | None = None,
                 expected_map_uid: str | None = None) -> list[float]:
    """Physical (unnormalized) feature vector, in FIELDS order."""
    if expected_map_uid is not None and state.get("map_uid") != expected_map_uid:
        raise ObservationError("map uid mismatch")
    if expected_tick_ms is not None and state.get("tick_ms") != expected_tick_ms:
        raise ObservationError(f"stale state: tick {state.get('tick_ms')} != {expected_tick_ms}")
    rot = _matrix(state)
    v_world = _vec3(state, "velocity")
    w_world = _vec3(state, "angular_velocity")
    gear = state.get("gear")
    if type(gear) is not int:
        raise ObservationError("missing or invalid: gear")
    tr = _num(state, "turning_rate")
    for name, x in (("lateral", proj.lateral_m), ("vertical", proj.vertical_m),
                    ("progress", proj.progress)):
        if not math.isfinite(x):
            raise ObservationError(f"non-finite projection: {name}")
    out = []
    out += vec.mat_T_vec(rot, v_world)
    out += vec.column(rot, 2)
    out += vec.column(rot, 1)
    out += vec.mat_T_vec(rot, w_world)
    out += [float(gear), tr, proj.lateral_m, proj.vertical_m, proj.progress]
    out += _bools(state, "wheel_contact")
    out += _bools(state, "wheel_sliding")
    if len(out) != DIM:
        raise ObservationError("internal dimension error")
    return out


def feature_names() -> list[str]:
    names = []
    for name, _label, width, *_ in FIELDS:
        if width == 1:
            names.append(name)
        elif width == 3:
            names += [f"{name}.{a}" for a in "xyz"]
        else:
            names += [f"{name}.{w}" for w in ("FL", "FR", "BR", "BL")]
    return names


# ---------------------------------------------------------------- normalization

def fit_normalization(rows: list[list[float]], *, data_kind: str, sources: list[str],
                      map_uid: str, reference_sha256: str) -> dict:
    """Per-feature mean/std for 'zscore' fields; identity elsewhere. rows = raw_features."""
    if data_kind not in ("real_human", "real_policy", "synthetic"):
        raise ValueError("data_kind must say where the statistics come from")
    if not rows:
        raise ValueError("no rows")
    names = feature_names()
    methods = []
    for _name, _label, width, *_rest, method in FIELDS:
        methods += [method] * width
    n = len(rows)
    mean, std, lo, hi = [], [], [], []
    for j in range(DIM):
        col = [r[j] for r in rows]
        m = math.fsum(col) / n
        sd = math.sqrt(math.fsum((x - m) ** 2 for x in col) / n)
        mean.append(m)
        std.append(sd)
        lo.append(min(col))
        hi.append(max(col))
    features = []
    for j in range(DIM):
        if methods[j] == "zscore":
            scale = max(std[j], 1e-3)
            features.append({"name": names[j], "method": "zscore", "offset": mean[j],
                             "scale": scale, "observed_min": lo[j], "observed_max": hi[j]})
        else:
            features.append({"name": names[j], "method": "identity", "offset": 0.0,
                             "scale": 1.0, "observed_min": lo[j], "observed_max": hi[j]})
    body = {"schema": NORMALIZATION_SCHEMA, "observation_schema": SCHEMA_VERSION,
            "data_kind": data_kind, "sources": sources, "samples": n, "map_uid": map_uid,
            "reference_sha256": reference_sha256, "clip": CLIP, "features": features}
    body["sha256"] = _hash({k: v for k, v in body.items() if k != "sha256"})
    return body


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def check_normalization(norm: dict) -> None:
    if norm.get("schema") != NORMALIZATION_SCHEMA or norm.get("observation_schema") != SCHEMA_VERSION:
        raise ObservationError("normalization schema mismatch")
    if _hash({k: v for k, v in norm.items() if k != "sha256"}) != norm.get("sha256"):
        raise ObservationError("normalization hash mismatch")
    if [f["name"] for f in norm["features"]] != feature_names():
        raise ObservationError("normalization feature order mismatch")


def normalize(raw: list[float], norm: dict) -> list[float]:
    c = norm["clip"]
    out = []
    for x, f in zip(raw, norm["features"], strict=True):
        y = (x - f["offset"]) / f["scale"]
        out.append(max(-c, min(c, y)))
    return out


class Encoder:
    """Frozen schema + frozen normalization. Same inputs give the same vector."""

    def __init__(self, norm: dict, map_uid: str):
        check_normalization(norm)
        if norm["map_uid"] != map_uid:
            raise ObservationError("normalization belongs to another map")
        self.norm = norm
        self.map_uid = map_uid

    def encode(self, state: dict, proj: Projection, expected_tick_ms: int | None = None):
        raw = raw_features(state, proj, expected_tick_ms=expected_tick_ms,
                           expected_map_uid=self.map_uid)
        return normalize(raw, self.norm)
