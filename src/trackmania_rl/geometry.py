"""Projection onto a prepared reference line: progress and signed offsets.

Generic: the reference (points, car-up vectors, cumulative length, checkpoint sectors)
comes from a prepared reference file; nothing here knows a particular map.

Local frame at the projected point (explicit, valid on slopes and banked turns):
  T = unit tangent of the reference segment (direction of travel),
  N = reference car "up" interpolated at the point, made orthogonal to T,
  L = N x T, pointing to the LEFT of the direction of travel.
The car basis measured in game is (x = left, y = up, z = forward), right-handed, so
L has the same sense as the car x axis for a car aligned with the reference.
  lateral_m  = (p - q) . L   > 0: left of the reference
  vertical_m = (p - q) . N   > 0: above the reference, along the local normal
Progress = arc length of q from the start (m) or divided by the total length. It may
decrease. It never validates a checkpoint: the checkpoint count is an input from the game
and bounds the searchable sector.

Search: only segments inside a continuity window around the previous projection and
inside the sector allowed by the game's checkpoint count. The globally nearest point is
never used, so a crossing or overpass of another part of the track cannot capture the
projection. If the best candidate in the window is too far (respawn, teleport), the
tracker relocalizes inside the allowed sector only and reports it.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass, field

from . import vec

GEOMETRY_VERSION = "trackmania_rl.geometry/1"
DEFAULT_PARAMS = {
    "max_speed_mps": 280.0,       # ~1000 km/h, upper bound of plausible car speed
    "window_slack_m": 8.0,        # added to the speed bound, forward and backward
    "start_window_m": 30.0,       # search window after reset
    "sector_margin_m": 15.0,      # tolerance around the reference checkpoint abscissa
    "relocalize_distance_m": 40.0,
}


class ProjectionError(RuntimeError):
    """Tracker used out of contract: no reset, time going back, bad checkpoint count."""


@dataclass
class Projection:
    s_m: float
    progress: float
    lateral_m: float
    vertical_m: float
    distance_m: float
    segment: int
    sector: int
    relocalized: bool
    frame: dict = field(default_factory=dict)


class ReferenceLine:
    def __init__(self, prepared: dict):
        self.points = prepared["points"]
        self.ups = prepared["ups"]
        self.s = prepared["s"]
        self.bounds = prepared["sector_bounds_m"]
        self.length = self.s[-1]
        self.sha256 = prepared.get("sha256")
        if len(self.points) < 2 or not len(self.points) == len(self.s) == len(self.ups):
            raise ValueError("invalid prepared reference")
        self.tangents = []
        for a, b in zip(self.points, self.points[1:]):
            self.tangents.append(vec.normalize(vec.sub(b, a), fallback=[0.0, 0.0, 1.0]))

    @property
    def sectors(self) -> int:
        return len(self.bounds) - 1

    def segment_range(self, s_lo: float, s_hi: float) -> range:
        """Segments intersecting [s_lo, s_hi] (granularity: one segment of the line)."""
        lo = max(0, bisect.bisect_right(self.s, s_lo) - 1)
        hi = min(len(self.points) - 2, max(lo, bisect.bisect_left(self.s, s_hi) - 1))
        return range(lo, hi + 1)

    def point_at(self, s_m: float):
        """Point of the line at arc length s_m (clamped to [0, length])."""
        s_m = max(0.0, min(self.length, s_m))
        i = min(len(self.points) - 2, max(0, bisect.bisect_right(self.s, s_m) - 1))
        span = self.s[i + 1] - self.s[i]
        return vec.lerp(self.points[i], self.points[i + 1], (s_m - self.s[i]) / span if span > 0 else 0.0)

    def frame_at(self, i: int, t: float):
        T = self.tangents[i]
        up = vec.lerp(self.ups[i], self.ups[i + 1], t)
        N = vec.sub(up, vec.scale(T, vec.dot(up, T)))
        N = vec.normalize(N, fallback=_any_normal(T))
        L = vec.cross(N, T)
        return T, N, L

    def project_on(self, p, i: int):
        a, b = self.points[i], self.points[i + 1]
        t, q = vec.project_on_segment(p, a, b)
        return t, q, vec.norm(vec.sub(p, q))

    def best_in(self, p, segments):
        best = None
        for i in segments:
            t, q, d = self.project_on(p, i)
            if best is None or d < best[2] - 1e-12:
                best = (i, t, d, q)
        return best


def _any_normal(T):
    guess = [0.0, 1.0, 0.0] if abs(T[1]) < 0.9 else [1.0, 0.0, 0.0]
    return vec.normalize(vec.sub(guess, vec.scale(T, vec.dot(guess, T))))


class ProgressTracker:
    """Stateful projection for one episode. Call reset() at every environment reset."""

    def __init__(self, line: ReferenceLine, params: dict | None = None):
        self.line = line
        self.p = dict(DEFAULT_PARAMS, **(params or {}))
        self.last: Projection | None = None
        self.last_race_ms: int | None = None
        self.max_s_m = 0.0          # diagnostic only; never fed back as the observation
        self.active = False

    def reset(self) -> None:
        self.last = None
        self.last_race_ms = None
        self.max_s_m = 0.0
        self.active = True

    def sector_range(self, checkpoints: int):
        if not 0 <= checkpoints <= self.line.sectors:
            raise ProjectionError(f"checkpoint count {checkpoints} outside 0..{self.line.sectors}")
        k = min(checkpoints, self.line.sectors - 1)
        m = self.p["sector_margin_m"]
        lo = self.line.bounds[k] - m if k > 0 else 0.0
        hi = self.line.bounds[k + 1] + m if k + 1 < self.line.sectors else self.line.length
        return k, max(0.0, lo), min(self.line.length, hi)

    def update(self, position, race_ms: int, checkpoints: int) -> Projection:
        if not self.active:
            raise ProjectionError("reset() required before update()")
        if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in position):
            raise ProjectionError("non-finite position")
        if self.last_race_ms is not None and race_ms < self.last_race_ms:
            raise ProjectionError("race time went back without reset()")
        sector, s_lo, s_hi = self.sector_range(checkpoints)
        if self.last is None:
            w_lo, w_hi = 0.0, self.p["start_window_m"]
        else:
            dt = (race_ms - self.last_race_ms) / 1000.0
            reach = self.p["max_speed_mps"] * dt + self.p["window_slack_m"]
            w_lo, w_hi = self.last.s_m - reach, self.last.s_m + reach
        lo, hi = max(w_lo, s_lo), min(w_hi, s_hi)
        relocalized = False
        best = None
        if lo <= hi:
            best = self.line.best_in(position, self.line.segment_range(lo, hi))
        if best is None or best[2] > self.p["relocalize_distance_m"]:
            alt = self.line.best_in(position, self.line.segment_range(s_lo, s_hi))
            if best is None or alt[2] < best[2]:
                best, relocalized = alt, True
        i, t, d, q = best
        T, N, L = self.line.frame_at(i, t)
        r = vec.sub(position, q)
        s_m = self.line.s[i] + t * (self.line.s[i + 1] - self.line.s[i])
        proj = Projection(s_m=s_m, progress=s_m / self.line.length,
                          lateral_m=vec.dot(r, L), vertical_m=vec.dot(r, N), distance_m=d,
                          segment=i, sector=sector, relocalized=relocalized,
                          frame={"T": T, "N": N, "L": L, "q": q})
        self.last, self.last_race_ms = proj, race_ms
        self.max_s_m = max(self.max_s_m, s_m)
        return proj
