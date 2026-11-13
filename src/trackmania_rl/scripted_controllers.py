"""Scripted TEST controllers for environment integration runs. NOT LEARNED, NOT A POLICY.

They exist only to exercise the environment contract in the real game (reset, transitions,
finish, abandon, truncation, incidents). None of them is trained, none of them is a
candidate driver and their runs are never learning data or performance evidence.

`reference_pursuit_v1` steers towards a point of the reference line ahead of the car (pure
pursuit on geometry, full throttle). It reads the reference line and the raw state; it is a
test harness and does not use the model observation vector.
"""
from __future__ import annotations

import bisect
import math

from . import vec
from .protocol import Action

LEARNED = False


class ScriptedController:
    name = "scripted"
    learned = LEARNED

    def act(self, env) -> Action:
        raise NotImplementedError

    def describe(self) -> dict:
        return {"name": self.name, "learned": self.learned, "kind": "scripted test controller"}


class Idle(ScriptedController):
    """No input at all: used to trigger the no-progress abandon rule."""
    name = "idle_v1"

    def __init__(self, ticks: int = 5):
        self.ticks = ticks

    def act(self, env) -> Action:
        return Action(0.0, False, False, self.ticks)


class FullGasStraight(ScriptedController):
    """Constant full throttle, wheels straight (open loop)."""
    name = "full_gas_straight_v1"

    def __init__(self, ticks: int = 5):
        self.ticks = ticks

    def act(self, env) -> Action:
        return Action(0.0, True, False, self.ticks)


class ReferencePursuit(ScriptedController):
    """Pure pursuit towards the reference line, full throttle. Scripted, not learned."""
    name = "reference_pursuit_v1"

    def __init__(self, line, ticks: int = 5, lookahead_m: float = 12.0,
                 lookahead_s: float = 0.35, gain: float = 2.5):
        self.line, self.ticks = line, ticks
        self.lookahead_m, self.lookahead_s, self.gain = lookahead_m, lookahead_s, gain

    def describe(self) -> dict:
        return {**super().describe(), "lookahead_m": self.lookahead_m,
                "lookahead_s": self.lookahead_s, "gain": self.gain}

    def point_at(self, s_m: float):
        s = self.line.s
        s_m = min(max(s_m, 0.0), s[-1])
        i = min(max(bisect.bisect_right(s, s_m) - 1, 0), len(s) - 2)
        t = (s_m - s[i]) / max(s[i + 1] - s[i], 1e-9)
        return vec.lerp(self.line.points[i], self.line.points[i + 1], t)

    def steer(self, state: dict, s_m: float) -> float:
        rot = state["rotation_matrix"]
        speed = vec.norm(state["velocity"])
        target = self.point_at(s_m + self.lookahead_m + self.lookahead_s * speed)
        d = vec.sub(target, state["position"])
        left, fwd = vec.dot(d, vec.column(rot, 0)), vec.dot(d, vec.column(rot, 2))
        angle = math.atan2(left, fwd)          # > 0: target on the left
        return max(-1.0, min(1.0, -self.gain * angle))   # steer < 0 = left

    def act(self, env) -> Action:
        return Action(self.steer(env.last_state, env.last_projection.s_m), True, False,
                      self.ticks)
