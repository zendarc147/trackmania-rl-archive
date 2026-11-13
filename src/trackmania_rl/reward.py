"""Reward v1: potential-based progress shaping, simulated-time cost, valid-finish bonus.

Decomposed and versioned (docs/REWARDS.md, decision D17). Generic: no map constant here.

Per transition s -> s' lasting dt simulated seconds:
  gamma_dt   = discount_per_second ** dt            (same per-second discount at any cadence)
  Phi(s)     = progress_scale * progress(s)          (progress in [0, 1] from the tracker)
  Phi(s')    = 0 when s' is terminal (finished or abandoned), else progress_scale * progress(s')
  progress   = gamma_dt * Phi(s') - Phi(s)           (potential-based shaping)
  time       = -time_cost_per_s * dt
  finish     = finish_bonus if the game confirmed a valid finish, else 0
  total      = progress + time + finish
The learner must use `discount` from the transition: 0 when terminated, gamma_dt otherwise
(a time-limit truncation keeps gamma_dt and bootstraps; it is not terminal).

With Phi(terminal) = 0 the shaping telescopes to -Phi(s0) over any terminated episode, so it
never pays for itself: an abandon returns the progress already collected, a loop returns less
than nothing. The objective left is time cost + finish bonus.

Night run of 2026-09-30 (J4-07): with that objective an agent that never finishes only learns
"end the episode sooner" (standing still until the abandon beats driving). Reward v2
(progress_mode = "delta", schema reward/2, user request of 2026-09-30) pays progress directly:
  progress   = progress_scale * (progress(s') - progress(s))   on every transition, abandon included
  time, finish and discount as in v1.
Going backwards costs what going forwards paid, so loops still pay nothing; progress is bounded
by the line, so delaying the finish never pays. v1 stays the default (old runs keep their hash).

Reward v3 (schema reward/3, user request of 2026-10-01) = v2 + a lap-time term that weighs
tenths more as the projected lap time gets close to a fixed target (the map's record):
  eta        = race_s + target * (1 - tau_ref(s_m) / T_ref)   projected lap time at target pace
               (tau_ref: time of the reference run at s_m; eta = race_s at the finish)
  Phi_lap    = -lap_scale * ln(1 + g / m)  for g = eta - target >= 0, -lap_scale * g / m below
  lap        = Phi_lap(eta') - Phi_lap(eta)
On an abandon eta' = max(eta', time limit): an abandon counts as the slowest admissible finish,
so it never stops the lap term on an optimistic projection. Slope lap_scale / (m + g): 0.1 s
weighs ~25x more at the target than 6 s away (lap_scale 12.5, m 0.25). The target is fixed for
an experiment (stationary reward). Going back raises eta by what going forward lowered.

What the reward never reads: wheel contact, sliding, steering changes, lateral offset,
speed. Those are observations only (REWARDS §3, decision D07).
"""
from __future__ import annotations

import bisect
import hashlib
import json
import math
from dataclasses import asdict, dataclass

REWARD_SCHEMA = "trackmania_rl.reward/1"
REWARD_SCHEMA_V2 = "trackmania_rl.reward/2"
REWARD_SCHEMA_V3 = "trackmania_rl.reward/3"
LAP_FIELDS = ("lap_scale", "lap_margin_s", "target_time_s")
PROGRESS_MODES = ("potential", "delta")

RUNNING = "running"
FINISHED = "finished"
ABANDONED = "abandoned"
TIME_LIMIT = "time_limit"
OUTCOMES = (RUNNING, FINISHED, ABANDONED, TIME_LIMIT)
TERMINAL = (FINISHED, ABANDONED)


@dataclass(frozen=True)
class RewardConfig:
    progress_scale: float = 100.0
    time_cost_per_s: float = 1.0
    finish_bonus: float = 150.0
    discount_per_second: float = 0.98
    terminal_potential: str = "zero"
    progress_mode: str = "potential"     # "potential" = reward/1, "delta" = reward/2
    lap_scale: float = 0.0               # > 0 = reward/3 (lap-time term, delta mode only)
    lap_margin_s: float = 0.25
    target_time_s: float = 0.0

    def __post_init__(self):
        for name in ("progress_scale", "time_cost_per_s", "finish_bonus", "discount_per_second",
                     *LAP_FIELDS):
            v = getattr(self, name)
            if type(v) not in (int, float) or not math.isfinite(v) or v < 0:
                raise ValueError(f"invalid reward parameter {name}")
        if not 0 < self.discount_per_second <= 1:
            raise ValueError("discount_per_second must be in (0, 1]")
        if self.terminal_potential != "zero":
            raise ValueError("only terminal_potential='zero' is implemented")
        if self.progress_mode not in PROGRESS_MODES:
            raise ValueError(f"progress_mode must be one of {PROGRESS_MODES}")
        if self.lap_scale and (self.progress_mode != "delta" or self.lap_margin_s <= 0
                               or self.target_time_s <= 0):
            raise ValueError("lap_scale needs progress_mode='delta', lap_margin_s > 0 and "
                             "target_time_s > 0")

    def gamma(self, dt_s: float) -> float:
        return self.discount_per_second ** dt_s

    def potential(self, progress: float) -> float:
        return self.progress_scale * progress

    def lap_potential(self, eta_s: float) -> float:
        g = eta_s - self.target_time_s
        m = self.lap_margin_s
        return -self.lap_scale * (math.log1p(g / m) if g >= 0 else g / m)

    def to_dict(self) -> dict:
        schema = (REWARD_SCHEMA_V3 if self.lap_scale else
                  REWARD_SCHEMA_V2 if self.progress_mode == "delta" else REWARD_SCHEMA)
        body = {"schema": schema, **asdict(self)}
        if not self.lap_scale:                   # reward/1 and /2 hashes stay those of old runs
            for k in LAP_FIELDS:
                del body[k]
        if self.progress_mode == "potential":
            del body["progress_mode"]
        body["sha256"] = hashlib.sha256(
            json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return body


@dataclass(frozen=True)
class RewardBreakdown:
    progress: float
    time: float
    finish: float
    total: float
    discount: float     # multiplier of the next state's value for the learner
    lap: float = 0.0    # reward/3 lap-time term (included in total)

    def to_dict(self) -> dict:
        return asdict(self)


def compute(cfg: RewardConfig, prev_progress: float, next_progress: float, dt_s: float,
            outcome: str, *, prev_eta_s: float | None = None, next_eta_s: float | None = None,
            time_limit_s: float | None = None) -> RewardBreakdown:
    """reward/3 also needs the projected lap times (see LapGhost) and, for an abandon, the
    episode time limit."""
    if outcome not in OUTCOMES:
        raise ValueError(f"unknown outcome {outcome}")
    if (not all(math.isfinite(x) for x in (prev_progress, next_progress, dt_s))
            or dt_s < 0 or (dt_s == 0 and (outcome != FINISHED
                                           or next_progress != prev_progress))):
        raise ValueError("non-finite progress or invalid duration")
    g = cfg.gamma(dt_s)
    if cfg.progress_mode == "delta":
        shaping = cfg.potential(next_progress) - cfg.potential(prev_progress)
    else:
        phi_next = 0.0 if outcome in TERMINAL else cfg.potential(next_progress)
        shaping = g * phi_next - cfg.potential(prev_progress)
    time = -cfg.time_cost_per_s * dt_s
    finish = cfg.finish_bonus if outcome == FINISHED else 0.0
    lap = 0.0
    if cfg.lap_scale:
        need = (prev_eta_s, next_eta_s) + ((time_limit_s,) if outcome == ABANDONED else ())
        if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in need):
            raise ValueError("reward/3 needs finite projected lap times (and time limit)")
        if outcome == ABANDONED:
            next_eta_s = max(next_eta_s, time_limit_s)
        lap = cfg.lap_potential(next_eta_s) - cfg.lap_potential(prev_eta_s)
    return RewardBreakdown(progress=shaping, time=time, finish=finish,
                           total=shaping + time + finish + lap,
                           discount=0.0 if outcome in TERMINAL else g, lap=lap)


class LapGhost:
    """Reference run timing along the line, for the reward/3 projected lap time.

    s_m and t_s: increasing arc lengths of the reference run and the race time it first
    reached them; ref_time_s: its finish time. Generic: the map supplies the data.
    """

    def __init__(self, s_m: list[float], t_s: list[float], length_m: float, ref_time_s: float):
        if (len(s_m) != len(t_s) or len(s_m) < 2 or ref_time_s <= 0
                or any(b <= a for a, b in zip(s_m, s_m[1:]))
                or any(b < a for a, b in zip(t_s, t_s[1:]))):
            raise ValueError("invalid lap ghost")
        self.s, self.t, self.length, self.ref_time_s = list(s_m), list(t_s), length_m, ref_time_s

    def tau(self, s_m: float) -> float:
        """Reference time at s_m (linear between samples, clamped to [0, ref_time_s])."""
        s = min(max(s_m, 0.0), self.length)
        i = bisect.bisect_right(self.s, s)
        if i == 0:
            return self.t[0] * s / self.s[0] if self.s[0] > 0 else self.t[0]
        if i == len(self.s):
            a, b, ta, tb = self.s[-1], self.length, self.t[-1], self.ref_time_s
        else:
            a, b, ta, tb = self.s[i - 1], self.s[i], self.t[i - 1], self.t[i]
        return ta + (tb - ta) * ((s - a) / (b - a) if b > a else 0.0)

    def eta(self, cfg: RewardConfig, s_m: float, race_s: float) -> float:
        """Projected lap time if the rest is driven at target pace."""
        return race_s + cfg.target_time_s * (1.0 - self.tau(s_m) / self.ref_time_s)


def discounted_return(steps: list[RewardBreakdown]) -> float:
    """Return from the first state, discounting with each transition's own gamma_dt."""
    total, factor = 0.0, 1.0
    for b in steps:
        total += factor * b.total
        factor *= b.discount
    return total


def _time_cost_until(cfg: RewardConfig, t_s: float) -> float:
    """Discounted sum of the time cost over [0, t_s] (continuous approximation)."""
    k = -math.log(cfg.discount_per_second)
    if k == 0:
        return cfg.time_cost_per_s * t_s
    return cfg.time_cost_per_s * (1 - cfg.discount_per_second ** t_s) / k


def min_finish_bonus(cfg: RewardConfig, time_limit_s: float, no_progress_s: float) -> float:
    """Smallest finish bonus for which finishing at the time limit beats abandoning.

    From any state, the shaping term is the same (-Phi(s)) for a finish and for an abandon,
    because Phi(terminal) = 0. An abandon needs at least no_progress_s of simulated time.
    Finishing after the longest admissible delay (time_limit_s) must still be preferred:
      -C(time_limit) + B * gamma^time_limit > -C(no_progress)
    """
    g = cfg.discount_per_second ** time_limit_s
    return (_time_cost_until(cfg, time_limit_s) - _time_cost_until(cfg, no_progress_s)) / g


def check_calibration(cfg: RewardConfig, time_limit_s: float, no_progress_s: float) -> dict:
    need = min_finish_bonus(cfg, time_limit_s, no_progress_s)
    return {"finish_bonus": cfg.finish_bonus, "min_finish_bonus": need,
            "margin": cfg.finish_bonus - need, "ok": cfg.finish_bonus > need}


def break_even_pace(cfg: RewardConfig, no_progress_s: float) -> float:
    """reward/2: slowest steady pace (track fraction per simulated second) that is worth more
    than stopping until the no-progress abandon, from any state (infinite-horizon discounting).

    Driving at pace v: (S v - c) / k.  Stopping: -c (1 - d^T) / k.  Driving wins iff v > c d^T / S,
    with S = progress_scale, c = time_cost_per_s, d = discount_per_second, T = no_progress_s.
    """
    if cfg.progress_mode != "delta":
        raise ValueError("break_even_pace applies to progress_mode='delta'")
    return cfg.time_cost_per_s * cfg.discount_per_second ** no_progress_s / cfg.progress_scale
