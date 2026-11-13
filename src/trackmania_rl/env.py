"""Episode environment: reset and transition contract over the TMInterface bridge (sync mode).

Generic. Map-specific values (UID, checkpoint count, time limit, no-progress delay) come
from the map profile; the reward from reward.RewardConfig; the observation from
observation.Encoder; the projection from geometry.ProgressTracker. No learning library.

Transition contract (one call to step()):
  source state s (boundary or start, tick t0) -> action held for `action_ticks` physics steps
  -> next state s' with reason "boundary" (tick t0 + action_ticks * tick_ms exactly) or
  "finish" (the game confirmed the finish, possibly at t0 after a boundary callback).
  A real-time finish may still carry the preceding action_id. Same-tick finishes are bounded
  by one physics tick of movement and pay no additional progress or time reward.
  s' must carry the same episode, expected map UID, and valid checkpoint count.

Outcomes (status):
  finished    game says RaceFinished with all checkpoints          terminated, finish bonus
  abandoned   progress max not beaten for no_progress_ms (D27)      terminated (failure)
  time_limit  race time reached time_limit_ms (D27)                  truncated, bootstrap
  running     none of the above
  error       technical problem (transport, timeout, stale or inconsistent state, projection
              or observation error): valid=False, no reward, no next observation. The
              transition must be dropped. Inputs are released; a reset is required.
A reset never produces a transition: reset() returns the first observation of a new episode.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field

from . import reward as rw
from .bridge import BridgeError
from .geometry import ProgressTracker, ProjectionError
from .observation import (Encoder, ObservationError, SCHEMA_VERSION,
                          EPISODE_SCHEMA_VERSION, episode_features, observation_contract,
                          LOOKAHEAD_SCHEMA_VERSION, lookahead_features)
from .protocol import Action

ENV_SCHEMA = "trackmania_rl.env/1"
ERROR = "error"


class EnvUsageError(RuntimeError):
    """Programming error: step() without a ready episode, wrong action duration..."""


@dataclass(frozen=True)
class EpisodeRules:
    checkpoint_count: int
    time_limit_ms: int
    no_progress_ms: int
    no_progress_min_gain_m: float = 0.01

    @classmethod
    def from_profile(cls, profile: dict, **overrides) -> "EpisodeRules":
        ep = profile.get("episode")
        if not isinstance(ep, dict):
            raise ValueError("map profile has no 'episode' section")
        values = {"checkpoint_count": profile["checkpoint_count"],
                  "time_limit_ms": ep["time_limit_ms"],
                  "no_progress_ms": ep["no_progress_ms"]}
        if "no_progress_min_gain_m" in ep:
            values["no_progress_min_gain_m"] = ep["no_progress_min_gain_m"]
        values.update(overrides)
        return cls(**values)


@dataclass
class Transition:
    episode: int
    action_id: int
    action: Action
    valid: bool
    status: str
    obs: list[float] | None
    next_obs: list[float] | None
    reward: float | None
    reward_components: dict | None
    terminated: bool
    truncated: bool
    discount: float | None
    dt_ms: int | None
    race_ms: int | None
    info: dict = field(default_factory=dict)

    @property
    def done(self) -> bool:
        return self.terminated or self.truncated or not self.valid


class TrackmaniaEnv:
    def __init__(self, bridge, profile: dict, encoder: Encoder, tracker: ProgressTracker,
                 reward_cfg: rw.RewardConfig, rules: EpisodeRules, *, action_ticks: int = 5,
                 tick_ms: int = 10, step_timeout_s: float = 2.0, reset_timeout_s: float = 15.0,
                 first_episode: int = 1, observation_schema: str = SCHEMA_VERSION,
                 ghost: rw.LapGhost | None = None):
        if reward_cfg.lap_scale and ghost is None:
            raise EnvUsageError("reward/3 (lap_scale > 0) needs a LapGhost")
        self.ghost = ghost
        self.bridge = bridge
        self.map_uid = profile["uid"]
        self.encoder = encoder
        self.observation_schema = observation_schema
        self.observation_contract = observation_contract(observation_schema)
        self.tracker = tracker
        self.reward_cfg = reward_cfg
        self.rules = rules
        self.action_ticks = action_ticks
        self.tick_ms = tick_ms
        self.step_timeout_s = step_timeout_s
        self.reset_timeout_s = reset_timeout_s
        self.episode = first_episode - 1
        self.ready = False
        self.action_id = 0
        self.last_state: dict | None = None
        self.last_projection = None
        self.last_obs: list[float] | None = None
        self.best_s_m = 0.0
        self.best_race_ms = 0
        # Real-time mode (J4 evaluation of the decision latency): the game does not wait for
        # the client, so a boundary may come later than one hold. Accepted lag, in ms.
        self.realtime = False
        self.realtime_max_lag_ms = 0
        self.stats = {"relocalizations": 0, "max_distance_m": 0.0, "max_ds_m": 0.0,
                      "clipped_values": 0, "errors": {}}

    # ------------------------------------------------------------------ helpers
    def describe(self) -> dict:
        return {"schema": ENV_SCHEMA, "map_uid": self.map_uid, "action_ticks": self.action_ticks,
                "tick_ms": self.tick_ms, "rules": self.rules.__dict__,
                "reward": self.reward_cfg.to_dict(), "tracker_params": self.tracker.p,
                "normalization_sha256": self.encoder.norm["sha256"],
                "observation": self.observation_contract}

    def _encode_observation(self, state, proj, expected_tick_ms):
        obs = self.encoder.encode(state, proj, expected_tick_ms=expected_tick_ms)
        if self.observation_schema in (EPISODE_SCHEMA_VERSION, LOOKAHEAD_SCHEMA_VERSION):
            obs += episode_features(race_ms=state["race_ms"], best_race_ms=self.best_race_ms,
                                    no_progress_ms=self.rules.no_progress_ms,
                                    progress_s_m=proj.s_m, best_s_m=self.best_s_m,
                                    length_m=self.tracker.line.length)
        if self.observation_schema == LOOKAHEAD_SCHEMA_VERSION:
            obs += lookahead_features(self.tracker.line, proj.s_m, state)
        return obs

    def configure(self, action_timeout_ms: int = 1000, auto_restart: bool = True,
                  sync: bool = True, official_finish: bool = False) -> dict:
        """Sync mode (default, D20), no streaming. The plugin releases inputs after
        action_timeout_ms. sync=False is the real-time mode (the game never waits); it also
        sets self.realtime, so boundaries up to realtime_max_lag_ms late are accepted.

        auto_restart (bridge >= 0.2.0): after a controlled finish the plugin rewinds to the
        countdown, so the next reset() works; without it the end-of-race dialog blocks resets.
        """
        if official_finish and auto_restart:
            raise ValueError("official_finish conflicts with auto_restart")
        kwargs = {"official_finish": True} if official_finish else {}
        ev = self.bridge.configure(sync=sync, timeout_ms=action_timeout_ms, stream_every=0,
                                   auto_restart=auto_restart, **kwargs)
        if official_finish and ev.get("official_finish") is not True:
            raise BridgeError("official finish mode not confirmed by bridge")
        if ev.get("sync") is not sync or ev.get("stream_every") != 0:
            raise BridgeError(f"bridge refused sync={sync} configuration: {ev}")
        self.realtime = not sync
        if auto_restart and ev.get("auto_restart") is not True:
            raise BridgeError(f"bridge does not support auto_restart (needs >= 0.2.0): {ev}")
        return ev

    def release(self) -> None:
        """Best effort: never raises. Inputs are also released by the plugin on timeout."""
        try:
            self.bridge.send_line("REL")
        except (BridgeError, OSError):
            pass

    def _count_clip(self, obs: list[float]) -> None:
        c = self.encoder.norm["clip"]
        self.stats["clipped_values"] += sum(1 for x in obs if abs(x) >= c)

    # ------------------------------------------------------------------ reset
    def reset(self) -> tuple[list[float], dict]:
        self.release()
        self.ready = False
        self.episode += 1
        self.action_id = 0
        pending = getattr(self.bridge, "pending", None)
        if pending is not None:
            pending.clear()     # messages of the previous episode never leak into this one
        try:
            state = self.bridge.reset(self.episode, timeout=self.reset_timeout_s)
        except (BridgeError, ValueError) as exc:
            self.release()
            raise BridgeError(f"reset failed: {exc}") from exc
        problems = []
        if state.get("map_uid") != self.map_uid:
            problems.append(f"map uid {state.get('map_uid')!r}")
        if state.get("race_ms") != 0:
            problems.append(f"race_ms {state.get('race_ms')} != 0")
        if state.get("checkpoints") != 0 or state.get("finished") is not False:
            problems.append("checkpoints or finish flag not cleared")
        if problems:
            self.release()
            raise BridgeError("invalid start state: " + "; ".join(problems))
        self.tracker.reset()
        try:
            proj = self.tracker.update(state["position"], state["race_ms"], state["checkpoints"])
            self.best_s_m, self.best_race_ms = proj.s_m, 0
            obs = self._encode_observation(state, proj, state["tick_ms"])
        except (ProjectionError, ObservationError, KeyError, TypeError) as exc:
            self.release()
            raise BridgeError(f"invalid start observation: {exc}") from exc
        self.last_state, self.last_projection, self.last_obs = state, proj, obs
        self._count_clip(obs)
        self.ready = True
        return obs, {"episode": self.episode, "state": state, "projection": proj}

    # ------------------------------------------------------------------ step
    def _exchange(self, action: Action) -> dict:
        ep, aid = self.episode, self.action_id
        line = action.encode(episode=ep, action_id=aid,
                             source_seq=self.last_state["seq"]).decode("ascii").strip()
        sent = self.bridge.send_line(line)

        def match(m: dict) -> bool:
            if m.get("episode") == ep:
                if m.get("event") == "action_rejected":
                    raise BridgeError(f"action rejected: {m.get('why')}")
                if m.get("event") == "released" and m.get("reason") != "client_request":
                    if m.get("reason") != "finish":
                        raise BridgeError(f"inputs released by game: {m.get('reason')}")
                    return False  # a finish state may be queued before or after this event
            return (m.get("kind") == "state" and m.get("reason") in ("boundary", "finish")
                    and m.get("episode") == ep
                    and (m.get("action_id") == aid or
                         (m.get("reason") == "finish" and aid > 1
                          and m.get("action_id") == aid - 1)))

        state = self.bridge.wait_for(match, self.step_timeout_s)
        state["_latency_s"] = state.get("_rx_mono", time.monotonic()) - sent
        return state

    def _check(self, prev: dict, st: dict) -> list[str]:
        p = []
        if st.get("map_uid") != self.map_uid:
            p.append("map uid mismatch")
        for key in ("tick_ms", "race_ms", "checkpoints", "seq"):
            if type(st.get(key)) is not int:
                p.append(f"missing integer {key}")
        if p:
            return p
        hold = self.action_ticks * self.tick_ms
        dtick = st["tick_ms"] - prev["tick_ms"]
        drace = st["race_ms"] - prev["race_ms"]
        if st["reason"] == "boundary":
            late = dtick - hold
            if self.realtime and 0 <= late <= self.realtime_max_lag_ms:
                pass    # real-time: the hold started when the action arrived, lag recorded
            elif dtick != hold:
                p.append(f"stale or skipped: tick delta {dtick} != {hold}")
            if drace != dtick:
                p.append(f"race time delta {drace} != tick delta {dtick}")
        else:   # finish, possibly mid-hold; race time freezes at the finish
            max_d = hold + (self.realtime_max_lag_ms if self.realtime else 0)
            if dtick == 0:
                # The checkpoint callback can follow a boundary at the same tick.
                # Position can reflect one physics step before the counters update.
                source_seq = (prev.get("source_seq") if st.get("action_id") == prev.get("action_id")
                              else prev["seq"])
                a, b = prev.get("position"), st.get("position")
                positions_valid = (isinstance(a, list) and isinstance(b, list)
                                   and len(a) == len(b) == 3
                                   and all(type(x) in (int, float) and math.isfinite(x)
                                           for x in a + b))
                distance = math.dist(a, b) if positions_valid else math.inf
                max_distance = self.tracker.p["max_speed_mps"] * self.tick_ms / 1000.0
                if (drace != 0 or st.get("source_seq") != source_seq
                        or not math.isfinite(distance) or distance > max_distance):
                    p.append("same-tick finish is not the state after the last boundary")
            elif not 0 < dtick <= max_d:
                p.append(f"finish tick delta {dtick} outside (0, {max_d}]")
            if not 0 <= drace <= dtick:
                p.append(f"finish race delta {drace} outside [0, {dtick}]")
        if st["seq"] <= prev["seq"]:
            p.append("sequence did not advance")
        if st["checkpoints"] < prev["checkpoints"]:
            p.append("checkpoint count decreased")
        if st["checkpoints"] > self.rules.checkpoint_count:
            p.append("checkpoint count above target")
        if type(st.get("finished")) is not bool:
            p.append("invalid finish flag")
        elif st["reason"] == "finish" and not st["finished"]:
            p.append("finish state without RaceFinished")
        elif st["finished"] and st["checkpoints"] != self.rules.checkpoint_count:
            p.append(f"finished with {st['checkpoints']}/{self.rules.checkpoint_count} checkpoints")
        return p

    def _fail(self, action: Action, reason: str, st: dict | None = None) -> Transition:
        self.release()
        self.ready = False
        kind = reason.split(":")[0]
        self.stats["errors"][kind] = self.stats["errors"].get(kind, 0) + 1
        return Transition(self.episode, self.action_id, action, valid=False, status=ERROR,
                          obs=self.last_obs, next_obs=None, reward=None, reward_components=None,
                          terminated=False, truncated=False, discount=None, dt_ms=None,
                          race_ms=None if st is None else st.get("race_ms"),
                          info={"error": reason})

    def step(self, action: Action) -> Transition:
        if not self.ready:
            raise EnvUsageError("step() requires a successful reset() and a running episode")
        if not isinstance(action, Action) or action.ticks != self.action_ticks:
            raise EnvUsageError(f"action must be protocol.Action with ticks={self.action_ticks}")
        self.action_id += 1
        prev, prev_proj = self.last_state, self.last_projection
        try:
            st = self._exchange(action)
        except (BridgeError, ValueError) as exc:
            return self._fail(action, f"transport: {exc}")
        problems = self._check(prev, st)
        if problems:
            return self._fail(action, "state: " + "; ".join(problems), st)
        same_tick_finish = st["reason"] == "finish" and st["tick_ms"] == prev["tick_ms"]
        finish_before_action = (st["reason"] == "finish" and st["action_id"] != self.action_id)
        try:
            proj = self.tracker.update(st["position"], st["race_ms"], st["checkpoints"])
            # boundary: exactly one hold later; finish: tick already bounded by _check;
            # real-time mode: the boundary tick itself (lag bounded by _check)
            expected = (prev["tick_ms"] + self.action_ticks * self.tick_ms
                        if st["reason"] == "boundary" and not self.realtime else st["tick_ms"])
            if self.tracker.max_s_m > self.best_s_m + self.rules.no_progress_min_gain_m:
                self.best_s_m, self.best_race_ms = self.tracker.max_s_m, st["race_ms"]
            obs = self._encode_observation(st, proj, expected)
        except (ProjectionError, ObservationError, KeyError, TypeError) as exc:
            return self._fail(action, f"observation: {exc}", st)

        # tracker diagnostics (J2-09 thresholds are still a proposal: measured here)
        self.stats["relocalizations"] += int(proj.relocalized)
        self.stats["max_distance_m"] = max(self.stats["max_distance_m"], proj.distance_m)
        self.stats["max_ds_m"] = max(self.stats["max_ds_m"], abs(proj.s_m - prev_proj.s_m))
        self._count_clip(obs)

        race = st["race_ms"]
        if st["finished"]:
            status = rw.FINISHED
        elif race - self.best_race_ms >= self.rules.no_progress_ms:
            status = rw.ABANDONED
        elif race >= self.rules.time_limit_ms:
            status = rw.TIME_LIMIT
        else:
            status = rw.RUNNING
        dt_ms = st["tick_ms"] - prev["tick_ms"]
        # The callback's extra position is diagnostic; its duration is unknown, so
        # do not pay a second progress increment for the same nominal tick.
        paid_progress = prev_proj.progress if same_tick_finish else proj.progress
        lap = {}
        if self.ghost is not None and self.reward_cfg.lap_scale:
            paid_s = prev_proj.s_m if same_tick_finish else proj.s_m
            lap = {"prev_eta_s": self.ghost.eta(self.reward_cfg, prev_proj.s_m,
                                                prev["race_ms"] / 1000.0),
                   "next_eta_s": (race / 1000.0 if status == rw.FINISHED else
                                  self.ghost.eta(self.reward_cfg, paid_s, race / 1000.0)),
                   "time_limit_s": self.rules.time_limit_ms / 1000.0}
        b = rw.compute(self.reward_cfg, prev_proj.progress, paid_progress, dt_ms / 1000.0,
                       status, **lap)
        terminated = status in rw.TERMINAL
        truncated = status == rw.TIME_LIMIT
        tr = Transition(self.episode, self.action_id, action, valid=True, status=status,
                        obs=self.last_obs, next_obs=obs, reward=b.total,
                        reward_components=b.to_dict(), terminated=terminated,
                        truncated=truncated, discount=b.discount, dt_ms=dt_ms, race_ms=race,
                        info={"progress": proj.progress, "s_m": proj.s_m,
                              "lateral_m": proj.lateral_m, "vertical_m": proj.vertical_m,
                              "relocalized": proj.relocalized, "checkpoints": st["checkpoints"],
                              "latency_s": st.get("_latency_s"), "reason": st["reason"],
                              "same_tick_finish": same_tick_finish,
                              "finish_before_action": finish_before_action,
                              "eta_s": lap.get("next_eta_s")})
        self.last_state, self.last_projection, self.last_obs = st, proj, obs
        if terminated or truncated:
            self.ready = False
            self.release()  # also disarm an action that raced with a finish event
        return tr
