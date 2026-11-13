"""Learner scheduling for the J4 SAC trainer: update ratio and parallel collection. Generic.

Config section `learner` (optional; absent = the historical J4 behaviour, driven by the
`sac.train_freq` / `sac.gradient_steps` values of the config):

  "learner": {
    "mode": "sync" | "async",
    "updates_per_transition": 0.5,   # UTD ratio: gradient steps per collected transition
    "max_update_lag": 32,            # async: the collector waits if the learner is behind
    "max_wait_ms": 250,              #   by more than this many updates, at most this long
    "actor_sync_every": 1,           # async: copy learner actor -> acting actor every N updates
    "chunk": 4                       # async: gradient steps per learner iteration (max)
  }

sync   one thread. After each stored transition, the trainer runs the gradient steps due
       so that updates = floor(ratio x transitions since learning_starts). Any ratio > 0
       (0.25, 0.5, 2...). SB3's own schedule is disabled (gradient_steps=0), so the
       transition budget is exact. Same order as the J4 loop for ratio 1.
async  the game is driven by the main thread with a frozen COPY of the actor; a learner
       thread runs the gradient steps concurrently. Wall time per transition becomes
       ~max(game, ratio x update) instead of their sum. The collector never waits longer
       than max_wait_ms per transition (the bridge releases inputs after its action
       timeout), so if the learner cannot keep up the realised ratio falls below the
       target; it is logged (learner/updates_per_transition), never hidden.

Consequences of async, recorded with the run: the acting policy lags the learner by at most
`actor_sync_every` updates plus the steps of one learner chunk; the order of gradient steps
relative to transitions depends on thread timing, so an async run is not bit-reproducible
from its seed. The replay buffer and the logger are locked so that the learner never samples
a transition while it is being written and never records while the collector dumps.
"""
from __future__ import annotations

import contextlib
import copy
import math
import threading
import time

from stable_baselines3.common.buffers import ReplayBuffer
from stable_baselines3.common.logger import Logger

LEARNER_SCHEMA = "trackmania_rl.learner/1"
DEFAULTS = {"mode": "sync", "updates_per_transition": 1.0, "max_update_lag": 32,
            "max_wait_ms": 250, "actor_sync_every": 1, "chunk": 4}


def learner_config(cfg: dict) -> dict | None:
    """Validated learner section, or None for the historical J4 behaviour."""
    raw = cfg.get("learner")
    if raw is None:
        return None
    unknown = set(raw) - set(DEFAULTS)
    if unknown:
        raise ValueError(f"learner: unknown keys {sorted(unknown)}")
    lc = {**DEFAULTS, **raw}
    if lc["mode"] not in ("sync", "async"):
        raise ValueError("learner.mode must be 'sync' or 'async'")
    r = float(lc["updates_per_transition"])
    if not (math.isfinite(r) and r > 0):
        raise ValueError("learner.updates_per_transition must be > 0")
    lc["updates_per_transition"] = r
    for key in ("max_update_lag", "actor_sync_every", "chunk"):
        if int(lc[key]) < 1:
            raise ValueError(f"learner.{key} must be >= 1")
        lc[key] = int(lc[key])
    if not 0 < float(lc["max_wait_ms"]) < 1000:
        raise ValueError("learner.max_wait_ms must be in (0, 1000): keep it under the bridge action timeout")
    sac = cfg.get("sac", {})
    clash = [k for k in ("train_freq", "gradient_steps") if k in sac]
    if clash:
        raise ValueError(f"learner.updates_per_transition replaces sac.{'/'.join(clash)}; remove them")
    return lc


class _Schedule:
    """Target number of gradient steps for the current session (resume-safe)."""

    def __init__(self, model, ratio: float):
        self.model, self.ratio = model, ratio
        self.n0 = int(model.num_timesteps)          # session start
        self.updates = 0                            # gradient steps done this session
        self.update_s = 0.0

    def target(self, n: int | None = None) -> int:
        n = self.model.num_timesteps if n is None else n
        start = max(int(self.model.learning_starts), self.n0)
        return int(self.ratio * max(0, n - start) + 1e-9)

    def lag(self) -> int:
        return self.target() - self.updates

    def base_stats(self) -> dict:
        n = self.model.num_timesteps
        eligible = max(0, n - max(int(self.model.learning_starts), self.n0))
        return {"updates_session": self.updates, "target_session": self.target(n),
                "lag_updates": self.target(n) - self.updates,
                "updates_per_transition": self.updates / eligible if eligible else None,
                "update_ms_mean": 1000 * self.update_s / self.updates if self.updates else None}


class SyncLearner(_Schedule):
    """Single thread: run the due gradient steps between two transitions."""

    def __init__(self, model, lc: dict):
        super().__init__(model, lc["updates_per_transition"])
        self.lc = lc

    def start(self):
        pass

    def check(self):
        pass

    def throttle(self):
        due = self.lag()
        if due > 0 and self.model.replay_buffer.size() >= self.model.batch_size:
            t0 = time.perf_counter()
            self.model.train(gradient_steps=due, batch_size=self.model.batch_size)
            self.update_s += time.perf_counter() - t0
            self.updates += due

    @contextlib.contextmanager
    def paused(self):
        yield

    def stop(self, timeout: float = 0.0):
        pass

    def stats(self) -> dict:
        return {**self.base_stats(), "collector_wait_s": 0.0, "collector_wait_timeouts": 0}


# ------------------------------------------------------------------ thread-safe SB3 pieces
class LockedReplayBuffer(ReplayBuffer):
    """ReplayBuffer whose add/sample are mutually exclusive (collector vs learner thread).

    The lock is not pickled; it is recreated lazily after loading, so a checkpoint written by
    an async run is also loadable by a sync run (it stays a ReplayBuffer subclass).
    """

    def _lk(self):
        lock = self.__dict__.get("_lock")
        if lock is None:
            lock = self.__dict__["_lock"] = threading.Lock()
        return lock

    def add(self, *args, **kwargs):
        with self._lk():
            return super().add(*args, **kwargs)

    def sample(self, *args, **kwargs):
        with self._lk():
            return super().sample(*args, **kwargs)

    def __getstate__(self):
        state = self.__dict__.copy()
        state.pop("_lock", None)
        return state


def make_locked(buffer: ReplayBuffer) -> ReplayBuffer:
    """Turn a loaded plain ReplayBuffer into a LockedReplayBuffer in place."""
    if type(buffer) is ReplayBuffer:
        buffer.__class__ = LockedReplayBuffer
    elif not isinstance(buffer, LockedReplayBuffer):
        raise TypeError(f"async learner supports ReplayBuffer only, got {type(buffer).__name__}")
    return buffer


class LockedLogger(Logger):
    """SB3 Logger safe for record() from the learner while the collector dumps."""

    def __init__(self, folder, output_formats):
        super().__init__(folder, output_formats)
        self._lock = threading.RLock()

    def record(self, *args, **kwargs):
        with self._lock:
            return super().record(*args, **kwargs)

    def record_mean(self, *args, **kwargs):
        with self._lock:
            return super().record_mean(*args, **kwargs)

    def dump(self, *args, **kwargs):
        with self._lock:
            return super().dump(*args, **kwargs)


# ------------------------------------------------------------------ async learner
class AsyncLearner(_Schedule):
    """Runs model.train() in a background thread at a target update/transition ratio."""

    def __init__(self, model, lc: dict):
        super().__init__(model, lc["updates_per_transition"])
        self.lc = lc
        self.train_lock = threading.Lock()          # held by each gradient chunk and by saves
        self.cond = threading.Condition()
        self.stop_event = threading.Event()
        self.error: BaseException | None = None
        self.wait_s = 0.0                           # collector time spent waiting for the learner
        self.wait_timeouts = 0
        self._since_sync = 0
        # frozen acting copy of the policy, used by model.predict() from the collector
        model.inference_policy = copy.deepcopy(model.policy)
        model.inference_policy.set_training_mode(False)
        model.inference_lock = threading.Lock()
        model.replay_buffer = make_locked(model.replay_buffer)
        self.thread = threading.Thread(target=self._run, name="sac-learner", daemon=True)

    # the learner thread never touches the game, the bridge or the run files
    def start(self):
        self.thread.start()

    def _sync_actor(self):
        with self.model.inference_lock:
            self.model.inference_policy.actor.load_state_dict(self.model.policy.actor.state_dict())
        self._since_sync = 0

    def _run(self):
        m = self.model
        try:
            while not self.stop_event.is_set():
                due = self.target() - self.updates
                if due <= 0 or m.replay_buffer.size() < m.batch_size:
                    with self.cond:
                        self.cond.wait(0.05)
                    continue
                k = min(due, self.lc["chunk"])
                t0 = time.perf_counter()
                with self.train_lock:
                    m.train(gradient_steps=k, batch_size=m.batch_size)
                self.update_s += time.perf_counter() - t0
                self.updates += k
                self._since_sync += k
                if self._since_sync >= self.lc["actor_sync_every"]:
                    self._sync_actor()
                with self.cond:
                    self.cond.notify_all()
        except BaseException as exc:          # surfaced in the collector thread
            self.error = exc
            with self.cond:
                self.cond.notify_all()

    def check(self):
        if self.error is not None:
            raise RuntimeError(f"learner thread failed: {type(self.error).__name__}: {self.error}") \
                from self.error

    def throttle(self):
        """Called by the collector after each stored transition, before the next action."""
        self.check()
        with self.cond:
            self.cond.notify_all()              # new data for the learner
            if self.lag() <= self.lc["max_update_lag"]:
                return
            t0 = time.monotonic()
            deadline = t0 + self.lc["max_wait_ms"] / 1000.0
            while self.lag() > self.lc["max_update_lag"] and self.error is None:
                left = deadline - time.monotonic()
                if left <= 0:
                    self.wait_timeouts += 1
                    break
                self.cond.wait(left)
            self.wait_s += time.monotonic() - t0
        self.check()

    @contextlib.contextmanager
    def paused(self):
        """Exclusive access to the model (checkpoint save): no gradient step in flight."""
        with self.train_lock:
            yield

    def stop(self, timeout: float = 30.0):
        self.stop_event.set()
        with self.cond:
            self.cond.notify_all()
        if self.thread.is_alive():
            self.thread.join(timeout)

    def stats(self) -> dict:
        return {**self.base_stats(), "collector_wait_s": self.wait_s,
                "collector_wait_timeouts": self.wait_timeouts}


def make_learner(model, lc: dict):
    return (AsyncLearner if lc["mode"] == "async" else SyncLearner)(model, lc)
