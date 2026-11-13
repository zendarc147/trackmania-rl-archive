"""Action codecs: learner output vector in [-1, 1]^n -> protocol.Action (D09, D25).

Generic, no map constant, no learning library. The game takes an analog steer and BINARY
gas and brake (J1-02). SAC (D15) outputs continuous values, so the binary commands need a
codec. D25 asks to compare two treatments:

  threshold_v1  3 outputs [steer, gas, brake]; gas = gas > 0, brake = brake > 0.
                Each binary command is an independent threshold on one continuous output.
  argmax4_v1    5 continuous scores, an earlier relaxation (not a hybrid SAC).
  hybrid4_v1    [steer, four one-hot commands encoded as -1/+1]; a separate SAC actor
                samples a categorical command and optimizes its exact expectation.

Both keep steer continuous in [-1, 1] -> round(steer * 65536) by protocol.Action. Neither
smooths or filters commands (OBSERVATIONS §6). The environment owns resets; no codec has a
respawn output.
"""
from __future__ import annotations

import math

from .protocol import Action

COMBOS = ((False, False), (True, False), (False, True), (True, True))   # (gas, brake)


class ActionCodec:
    name = "codec"
    dim = 0
    labels: tuple[str, ...] = ()

    def __init__(self, ticks: int = 5):
        self.ticks = ticks

    def _check(self, a) -> list[float]:
        v = [float(x) for x in a]
        if len(v) != self.dim or not all(math.isfinite(x) for x in v):
            raise ValueError(f"{self.name}: expected {self.dim} finite values, got {a!r}")
        return [max(-1.0, min(1.0, x)) for x in v]

    def decode(self, a) -> Action:
        raise NotImplementedError

    def describe(self) -> dict:
        return {"name": self.name, "dim": self.dim, "labels": list(self.labels),
                "ticks": self.ticks, "steer_scale": 65536}


class ThresholdCodec(ActionCodec):
    name = "threshold_v1"
    dim = 3
    labels = ("steer", "gas_score", "brake_score")

    def decode(self, a) -> Action:
        s, g, b = self._check(a)
        return Action(s, g > 0.0, b > 0.0, self.ticks)


class Argmax4Codec(ActionCodec):
    name = "argmax4_v1"
    dim = 5
    labels = ("steer", "score_coast", "score_gas", "score_brake", "score_gas_brake")

    def decode(self, a) -> Action:
        v = self._check(a)
        scores = v[1:]
        k = max(range(4), key=lambda i: (scores[i], -i))   # ties: lowest index, deterministic
        gas, brake = COMBOS[k]
        return Action(v[0], gas, brake, self.ticks)


class Hybrid4Codec(ActionCodec):
    name = "hybrid4_v1"
    dim = 5
    labels = ("steer", "coast", "gas", "brake", "gas_brake")

    def decode(self, a) -> Action:
        v = self._check(a)
        k = max(range(4), key=lambda i: (v[i + 1], -i))
        gas, brake = COMBOS[k]
        return Action(v[0], gas, brake, self.ticks)


CODECS = {c.name: c for c in (ThresholdCodec, Argmax4Codec, Hybrid4Codec)}


def make_codec(name: str, ticks: int = 5) -> ActionCodec:
    if name not in CODECS:
        raise ValueError(f"unknown action codec {name!r}; known: {sorted(CODECS)}")
    return CODECS[name](ticks)
