"""Gymnasium adapter over TrackmaniaEnv for learning libraries (J4). Generic, no map constant.

- Observation: the environment's approved v1 (25) or v2 (27) vector, float32.
  Base normalization stays frozen; v2 appends episode context (J4-15).
- Action: Box [-1, 1]^codec.dim, decoded by an actions.ActionCodec (D25).
- terminated: finished or abandoned. truncated: time limit (the learner bootstraps).
- Technical error (env status "error"): the transition is INVALID. It is returned with
  truncated=True and info["invalid"]=True so that the episode ends; the learner MUST drop it
  (training.FilteredSAC does). Its reward is reported as 0.0 only because gymnasium needs a
  float: it is never stored.
- reset(): TrackmaniaEnv.reset with bounded retries; each failure is reported to `on_incident`
  and `recover` (e.g. reconnect the bridge) is tried. A reset never produces a transition.
"""
from __future__ import annotations

import time
from typing import Callable

import gymnasium as gym
import numpy as np

from .actions import ActionCodec
from .bridge import BridgeError
from .env import TrackmaniaEnv


class TrackmaniaGymEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, env: TrackmaniaEnv, codec: ActionCodec, *, reset_attempts: int = 3,
                 reset_pause_s: float = 1.0, recover: Callable[[], None] | None = None,
                 on_transition: Callable | None = None, on_incident: Callable | None = None):
        super().__init__()
        clip = float(env.encoder.norm["clip"])
        self.env, self.codec = env, codec
        dim = env.observation_contract["dim"]
        self.observation_space = gym.spaces.Box(-clip, clip, (dim,), np.float32)
        self.action_space = gym.spaces.Box(-1.0, 1.0, (codec.dim,), np.float32)
        self.reset_attempts, self.reset_pause_s = reset_attempts, reset_pause_s
        self.recover = recover
        self.on_transition = on_transition or (lambda t, raw: None)
        self.on_incident = on_incident or (lambda kind, detail: None)
        self._last = np.zeros(dim, np.float32)

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        last_exc = None
        for attempt in range(1, self.reset_attempts + 1):
            try:
                obs, info = self.env.reset()
                self._last = np.asarray(obs, np.float32)
                return self._last.copy(), {"episode": info["episode"], "reset_attempt": attempt}
            except BridgeError as exc:
                last_exc = exc
                self.on_incident("reset_failed", {"attempt": attempt, "error": str(exc)})
                time.sleep(self.reset_pause_s)
                if self.recover is not None:
                    try:
                        self.recover()
                    except (BridgeError, OSError) as rexc:
                        self.on_incident("recover_failed", {"attempt": attempt, "error": str(rexc)})
        raise RuntimeError(f"reset failed {self.reset_attempts} times: {last_exc}")

    def step(self, action):
        raw = np.asarray(action, np.float64).reshape(-1)
        t = self.env.step(self.codec.decode(raw))
        self.on_transition(t, raw)
        if not t.valid:
            self.on_incident("invalid_transition", {"episode": t.episode, "action_id": t.action_id,
                                                    "error": t.info.get("error")})
            return self._last.copy(), 0.0, False, True, {"invalid": True, "status": t.status,
                                                          "error": t.info.get("error")}
        self._last = np.asarray(t.next_obs, np.float32)
        info = {"invalid": False, "status": t.status, "race_ms": t.race_ms,
                "progress": t.info.get("progress"), "dt_ms": t.dt_ms}
        return self._last.copy(), float(t.reward), bool(t.terminated), bool(t.truncated), info

    def close(self):
        self.env.release()
