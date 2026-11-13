"""J4 training loop: SAC (D15) from Stable-Baselines3 over TrackmaniaGymEnv. Generic.

Everything specific to a run comes from a JSON config (configs/training/*.json) and the map
profile it names. A run writes, without Hermes, everything needed to diagnose it:

  runs/<group>/<run_id>/
    config.json           config as given + resolved values (gamma, budget in sim time)
    versions.json         Python and library versions, bridge hello, file hashes
    status.json           live state (updated at every episode end and checkpoint)
    episodes.jsonl        one line per episode: status, race time, progress, return, ...
    transitions.jsonl     one line per transition (action, reward terms, status, latency);
                          observations live in the replay buffer, not here
    incidents.jsonl       invalid transitions, failed resets, reconnections, stops
    sb3/                  SB3 logger output: progress.csv + TensorBoard event files
    checkpoints/<n>/      model.zip (policy, critics, optimizers, entropy coef),
                          replay_buffer.pkl (latest checkpoint only), trainer_state.json
    checkpoints/latest.json
    STOP                  created by `tm.py stop`: the run saves and exits cleanly

Invalid transitions (env status "error") are never stored (FilteredSAC). Time-limit
truncations are stored with done=True and TimeLimit.truncated=True, so SB3 bootstraps them
(handle_timeout_termination). The SAC discount per step equals the reward discount of the
transition duration (reward v1: 0.98 per simulated second -> 0.98 ** 0.05 per 50 ms step;
reward v2 configs use 0.905 per second -> ~0.995 per 50 ms step).

Gradient schedule: without a `learner` section, SB3's own train_freq/gradient_steps (the
historical J4 loop, 1 update per transition). With one, SB3 only collects and learner.py
trains: `sync` between transitions, `async` in a background thread, at any
`updates_per_transition` ratio. Hybrid critic: `sac.hybrid_critic` "action_input" (default,
historical) or "q4" (one pass for the four commands). See learner.py and hybrid_sac.py.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import pathlib
import pickle
import platform
import signal
import statistics
import sys
import time
import uuid
from dataclasses import dataclass
from typing import Callable

import numpy as np

from . import reward as rw
from .actions import make_codec
from .gym_env import TrackmaniaGymEnv
from .learner import LEARNER_SCHEMA, LockedLogger, learner_config, make_learner
from .observation import (SCHEMA_VERSION, EPISODE_SCHEMA_VERSION, LOOKAHEAD_SCHEMA_VERSION,
                          observation_contract)

TRAINER_SCHEMA = "trackmania_rl.trainer/1"


class StopTraining(Exception):
    """Raised after a transition has been stored, when a clean stop was requested."""


def load_config(path) -> dict:
    return validate_config(json.loads(pathlib.Path(path).read_text(encoding="utf-8")), str(path))


def validate_config(cfg: dict, where: str = "config") -> dict:
    observation_contract(cfg.get("observation_schema", SCHEMA_VERSION))
    diagnostic = cfg.get("critic_diagnostics", {})
    if set(diagnostic) - {"every_updates", "samples"}:
        raise ValueError("unknown critic_diagnostics option")
    for key in ("every_updates", "samples"):
        if key in diagnostic and (type(diagnostic[key]) is not int or diagnostic[key] <= 0):
            raise ValueError(f"critic_diagnostics.{key} must be a positive integer")
    if diagnostic and cfg.get("action_codec") != "hybrid4_v1":
        raise ValueError("critic_diagnostics currently supports hybrid SAC only")
    for key in ("name", "map", "action_codec", "budget", "sac", "seed"):
        if key not in cfg:
            raise ValueError(f"training {where}: missing '{key}'")
    b = cfg["budget"]
    if b["transitions"] is not None and int(b["transitions"]) <= 0:
        raise ValueError("budget.transitions must be > 0")
    cap = b.get("cap_transitions")
    if b["transitions"] is not None and cap is not None and int(b["transitions"]) > int(cap):
        raise ValueError(f"budget.transitions {b['transitions']} exceeds the approved cap {cap}")
    if int(cfg.get("checkpoint_every_transitions", 10000)) <= 0:
        raise ValueError("checkpoint_every_transitions must be > 0")
    hc = cfg["sac"].get("hybrid_critic")
    if hc is not None:
        if hc not in HYBRID_CRITICS:
            raise ValueError(f"sac.hybrid_critic must be one of {HYBRID_CRITICS}")
        if cfg["action_codec"] != "hybrid4_v1":
            raise ValueError("sac.hybrid_critic applies to action_codec hybrid4_v1 only")
    if "hybrid_target_entropy" in cfg["sac"]:
        if cfg["action_codec"] != "hybrid4_v1":
            raise ValueError("sac.hybrid_target_entropy applies to action_codec hybrid4_v1 only")
        te = cfg["sac"]["hybrid_target_entropy"]
        if not (isinstance(te, list) and len(te) == 2 and te[0] < math.log(2)
                and 0 < te[1] < math.log(4)):
            raise ValueError("sac.hybrid_target_entropy must be [steer < ln 2, 0 < command < ln 4]")
    learner_config(cfg)          # raises on an invalid learner section
    exploration = cfg.get("exploration", {})
    if set(exploration) - {"command_bursts"}:
        raise ValueError("unknown exploration option")
    if "command_bursts" in exploration:
        if cfg["action_codec"] != "hybrid4_v1":
            raise ValueError("exploration.command_bursts applies to action_codec hybrid4_v1 only")
        validate_command_bursts(exploration["command_bursts"])
    init = cfg.get("init_from")
    if init is not None and (not isinstance(init, dict) or not init.get("run")):
        raise ValueError("init_from must be {\"run\": <run dir>, \"checkpoint\": <dir or latest>}")
    if init is not None and init.get("migration") not in (None, "observation_v2", "observation_v3",
                                                           "fresh_replay"):
        raise ValueError("unknown init_from.migration")
    if (init and init.get("migration") == "observation_v2"
            and cfg.get("observation_schema") != EPISODE_SCHEMA_VERSION):
        raise ValueError("observation_v2 migration requires observation schema v2")
    if (init and init.get("migration") == "observation_v3"
            and cfg.get("observation_schema") != LOOKAHEAD_SCHEMA_VERSION):
        raise ValueError("observation_v3 migration requires observation schema v3")
    return cfg


def init_checkpoint_dir(cfg: dict) -> pathlib.Path:
    """Checkpoint a new run starts from (config `init_from`); "latest" follows latest.json."""
    from .runtime import resolve
    run = resolve(cfg["init_from"]["run"])
    name = cfg["init_from"].get("checkpoint", "latest")
    if name == "latest":
        name = pathlib.Path(json.loads((run / "checkpoints" / "latest.json").read_text())["dir"]).name
    return run / "checkpoints" / name


def _airborne(state) -> bool:
    contact = (state or {}).get("wheel_contact")
    return bool(contact) and not any(contact)


def copy_replay_buffer(source, target) -> None:
    """Copy `source` transitions into the empty `target`, oldest first, keeping the most
    recent ones if `target` is smaller. Lets init_from change the buffer capacity."""
    n = source.size()
    order = (np.roll(np.arange(source.buffer_size), -source.pos) if source.full
             else np.arange(n))[-target.buffer_size:]
    for key in ("observations", "next_observations", "actions", "rewards", "dones", "timeouts"):
        getattr(target, key)[:len(order)] = getattr(source, key)[order]
    target.pos = len(order) % target.buffer_size
    target.full = len(order) == target.buffer_size


HYBRID_CRITICS = ("action_input", "q4")


def model_class_for(cfg: dict):
    """(algorithm class, policy) for a run config; also used to load checkpoints."""
    if cfg["action_codec"] == "hybrid4_v1":
        from .hybrid_sac import HybridPolicy, HybridQ4Policy, HybridQ4SAC, HybridSAC
        if cfg["sac"].get("hybrid_critic", "action_input") == "q4":
            return HybridQ4SAC, HybridQ4Policy
        return HybridSAC, HybridPolicy
    return make_filtered_sac_class(), "MlpPolicy"


def resolved(cfg: dict) -> dict:
    """Derived values recorded with the run (never edited by hand)."""
    reward_cfg = rw.RewardConfig(**cfg.get("reward", {}))
    ticks = int(cfg.get("action_ticks", 5))
    step_s = ticks * 10 / 1000.0
    return {"reward": reward_cfg.to_dict(), "action_ticks": ticks, "step_s": step_s,
            "observation": observation_contract(cfg.get("observation_schema", SCHEMA_VERSION)),
            "gamma_per_step": reward_cfg.gamma(step_s),
            "budget_sim_hours": (None if cfg["budget"]["transitions"] is None else
                                 int(cfg["budget"]["transitions"]) * step_s / 3600.0),
            "learner": learner_config(cfg) or {"mode": "legacy_sb3",
                                                "train_freq": cfg["sac"].get("train_freq", 1),
                                                "gradient_steps": cfg["sac"].get("gradient_steps", 1)},
            "learner_schema": LEARNER_SCHEMA}


def library_versions() -> dict:
    import gymnasium
    import stable_baselines3
    import torch
    return {"python": sys.version.split()[0], "platform": platform.platform(),
            "torch": torch.__version__, "torch_threads": torch.get_num_threads(),
            "cuda_available": torch.cuda.is_available(),
            "stable_baselines3": stable_baselines3.__version__,
            "gymnasium": gymnasium.__version__, "numpy": np.__version__}


class JsonlWriter:
    def __init__(self, path):
        self.f = open(path, "a", encoding="utf-8")

    def write(self, rec: dict) -> None:
        self.f.write(json.dumps(rec, separators=(",", ":"), default=str) + "\n")
        self.f.flush()

    def close(self):
        self.f.close()


def _write_json_atomic(path: pathlib.Path, obj) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=str), encoding="utf-8")
    os.replace(tmp, path)


def _pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1)))] if xs else None


@dataclass
class EnvHandle:
    """What an environment factory returns. `close` releases inputs and restores the game."""
    env: object                      # TrackmaniaEnv
    close: Callable[[], None]
    recover: Callable[[], None] | None = None
    info: dict | None = None


def command_burst(model, cfg: dict, action, buffer_action) -> None:
    """J6 exploration: occasionally hold one gas/brake command for a few steps (hybrid4 only).

    The TMX ghosts show a 100 ms gas release before the first crest that no policy found in
    millions of transitions (docs/reports/J6-chrono.md). With probability `start_prob` per
    step a burst of `min_steps..max_steps` steps forces one command from `commands`
    (indices of actions.COMBOS). Off-policy: the replay stores the action actually played.
    Steering is untouched. Edits both arrays in place (n_envs = 1).
    """
    rng = getattr(model, "_burst_rng", None)
    if rng is None:
        rng = model._burst_rng = np.random.default_rng(int(cfg.get("seed", 0)))
        model._burst_left, model._burst_cmd = 0, 0
        model._burst_steps = 0
    if model._burst_left <= 0 and rng.random() < cfg["start_prob"]:
        model._burst_left = int(rng.integers(cfg["min_steps"], cfg["max_steps"] + 1))
        model._burst_cmd = int(rng.choice(cfg["commands"]))
    if model._burst_left > 0:
        onehot = np.full(4, -1.0, dtype=np.float32)
        onehot[model._burst_cmd] = 1.0
        action[0, 1:5] = onehot
        buffer_action[0, 1:5] = onehot
        model._burst_left -= 1
        model._burst_steps += 1


def validate_command_bursts(b: dict) -> None:
    if set(b) - {"start_prob", "min_steps", "max_steps", "commands", "seed"}:
        raise ValueError("unknown exploration.command_bursts option")
    if not 0 < float(b["start_prob"]) < 1:
        raise ValueError("command_bursts.start_prob must be in (0, 1)")
    if not 1 <= int(b["min_steps"]) <= int(b["max_steps"]):
        raise ValueError("command_bursts needs 1 <= min_steps <= max_steps")
    if not b["commands"] or any(c not in (0, 1, 2, 3) for c in b["commands"]):
        raise ValueError("command_bursts.commands are actions.COMBOS indices 0..3")


def make_filtered_sac_class():
    from stable_baselines3 import SAC

    class FilteredSAC(SAC):
        """SAC that never stores invalid transitions and exposes a post-store hook.

        With the async learner (learner.AsyncLearner), `inference_policy` is a frozen copy of
        the policy used to act while the learner thread updates `policy`.
        """
        after_store: Callable | None = None
        inference_policy = None
        inference_lock = None
        _use_loaded_policy = False

        def _sample_action(self, learning_starts, action_noise=None, n_envs=1):
            # A migrated trained policy collects new-schema data while gradients wait;
            # this wait must not replace its actions with a new random warmup.
            action, buffer_action = super()._sample_action(
                0 if self._use_loaded_policy else learning_starts, action_noise, n_envs)
            bursts = getattr(self, "_command_bursts", None)
            if bursts:
                command_burst(self, bursts, action, buffer_action)
            return action, buffer_action

        def predict(self, observation, state=None, episode_start=None, deterministic=False):
            if self.inference_policy is None:
                return super().predict(observation, state, episode_start, deterministic)
            with self.inference_lock:
                return self.inference_policy.predict(observation, state, episode_start, deterministic)

        def _excluded_save_params(self):
            return [*super()._excluded_save_params(), "inference_policy", "inference_lock",
                    "_command_bursts", "_burst_rng", "_burst_left", "_burst_cmd", "_burst_steps"]

        def _store_transition(self, replay_buffer, buffer_action, new_obs, reward, dones, infos):
            if any(i.get("invalid") for i in infos):
                # Drop it: keep the (already reset) next observation as the new start.
                self._last_obs = new_obs
                self._last_original_obs = new_obs
                if self.after_store is not None:
                    self.after_store(dones, infos, stored=False)
                return
            super()._store_transition(replay_buffer, buffer_action, new_obs, reward, dones, infos)
            if self.after_store is not None:
                self.after_store(dones, infos, stored=True)

    return FilteredSAC


class Trainer:
    def __init__(self, cfg: dict, run_dir: pathlib.Path, env_factory: Callable[[int], EnvHandle],
                 *, resume: bool = False, extra_versions: dict | None = None,
                 install_signal_handler: bool = True):
        self.cfg, self.run_dir = cfg, pathlib.Path(run_dir)
        self.env_factory = env_factory
        self.resume = resume
        self.derived = resolved(cfg)
        self.codec = make_codec(cfg["action_codec"], self.derived["action_ticks"])
        self.budget = (None if cfg["budget"]["transitions"] is None else
                       int(cfg["budget"]["transitions"]))
        self.ckpt_every = int(cfg.get("checkpoint_every_transitions", 10000))
        self.log_transitions = bool(cfg.get("log_transitions", True))
        self.stop_requested = False
        self.stop_reason = None
        self.install_signal_handler = install_signal_handler
        self.extra_versions = extra_versions or {}
        # counters, restored on resume
        self.state = {"episodes": 0, "finishes": 0, "abandons": 0, "time_limits": 0,
                      "invalid_transitions": 0, "valid_transitions": 0, "failed_resets": 0,
                      "best_finish_ms": None, "last_episode_id": 0, "sim_ms": 0,
                      "wall_s_before": 0.0, "checkpoints": [], "rate_window": None}
        self.state["recent_finishes"] = []
        self._ep = self._new_episode()
        self._window = (time.monotonic(), 0)      # (wall, timesteps) for the live rate
        self._last_ckpt_at = 0
        self._record = None      # new best finish waiting for its policy snapshot
        self._t_start = time.monotonic()
        self.model = None
        self.learner_cfg = learner_config(cfg)
        self.learner = None      # SyncLearner or AsyncLearner when cfg has a learner section

    # ---------------------------------------------------------------- files
    def _open_files(self):
        self.run_dir.mkdir(parents=True, exist_ok=True)
        (self.run_dir / "checkpoints").mkdir(exist_ok=True)
        self.episodes_w = JsonlWriter(self.run_dir / "episodes.jsonl")
        self.incidents_w = JsonlWriter(self.run_dir / "incidents.jsonl")
        self.transitions_w = JsonlWriter(self.run_dir / "transitions.jsonl") if self.log_transitions else None

    def _close_files(self):
        for w in (self.episodes_w, self.incidents_w, self.transitions_w):
            if w is not None:
                w.close()

    def incident(self, kind: str, detail: dict) -> None:
        if kind == "reset_failed":
            self.state["failed_resets"] += 1
        self.incidents_w.write({"wall": time.strftime("%Y-%m-%dT%H:%M:%S"), "kind": kind,
                                "timesteps": self.model.num_timesteps if self.model else None,
                                **detail})

    def write_status(self, phase: str) -> None:
        wall = self.state["wall_s_before"] + (time.monotonic() - self._t_start)
        n = self.model.num_timesteps if self.model else 0
        _write_json_atomic(self.run_dir / "status.json", {
            "run_id": self.run_dir.name, "phase": phase, "pid": os.getpid(),
            "updated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "timesteps": n, "budget_transitions": self.budget,
            "budget_fraction": None if self.budget is None else n / self.budget,
            "sim_hours": self.state["sim_ms"] / 3.6e6,
            "wall_hours": wall / 3600.0, "stop_reason": self.stop_reason,
            "eta_hours": ((self.budget - n) / self.state["rate_window"] / 3600.0
                          if self.budget is not None and self.state.get("rate_window") else None),
            **{k: v for k, v in self.state.items() if k not in ("checkpoints", "wall_s_before")},
            "latest_checkpoint": self.state["checkpoints"][-1] if self.state["checkpoints"] else None})

    # ---------------------------------------------------------------- episode stats
    @staticmethod
    def _new_episode():
        return {"id": None, "steps": 0, "valid": 0, "components": [], "latency": [],
                "progress_max": 0.0, "t0": time.monotonic(), "action_counts": [0, 0, 0, 0],
                "steer_abs_sum": 0.0, "air": False, "air_steps": 0, "air_brake": 0}

    def on_transition(self, t, raw_action) -> None:
        ep = self._ep
        ep["id"] = t.episode
        ep["steps"] += 1
        a = t.action
        ep["action_counts"][int(a.accelerate) + 2 * int(a.brake)] += 1
        ep["steer_abs_sum"] += abs(a.steer)
        # brake while airborne (the action was chosen in the previous state); generic, J6
        ep["air_steps"] += ep["air"]
        ep["air_brake"] += ep["air"] and a.brake
        ep["air"] = _airborne(self.handle.env.last_state)
        if t.valid:
            ep["valid"] += 1
            self.state["valid_transitions"] += 1
            self.state["sim_ms"] += t.dt_ms
            ep["components"].append(t.reward_components)
            ep["progress_max"] = max(ep["progress_max"], t.info.get("progress") or 0.0)
            if t.info.get("latency_s") is not None:
                ep["latency"].append(t.info["latency_s"] * 1000.0)
        else:
            self.state["invalid_transitions"] += 1
        if self.transitions_w is not None:
            self.transitions_w.write({
                "episode": t.episode, "action_id": t.action_id, "valid": t.valid,
                "status": t.status, "raw_action": [round(float(x), 5) for x in raw_action],
                "action": [round(a.steer, 5), a.accelerate, a.brake],
                "reward": t.reward, "components": t.reward_components, "race_ms": t.race_ms,
                "dt_ms": t.dt_ms, "same_tick_finish": t.info.get("same_tick_finish", False),
                "finish_before_action": t.info.get("finish_before_action", False),
                "progress": t.info.get("progress"), "lateral_m": t.info.get("lateral_m"),
                "latency_ms": None if t.info.get("latency_s") is None else round(t.info["latency_s"] * 1000, 3),
                "error": t.info.get("error")})
        if t.done:
            self._end_episode(t)
        n = self.model.num_timesteps + 1 if self.model is not None else 0
        if self.model is not None and n % 500 == 0:
            # live metrics even during long episodes: rate over the window (includes the
            # SAC updates), SAC losses recorded by SB3 since the last dump
            w0, n0 = self._window
            now = time.monotonic()
            rate = (n - n0) / (now - w0) if now > w0 and n > n0 else None
            self._window = (now, n)
            self.state["rate_window"] = rate
            if rate:
                self.model.logger.record("throughput/transitions_per_wall_s_window", rate)
            self.model.logger.record("totals/sim_hours", self.state["sim_ms"] / 3.6e6)
            if self.learner is not None:
                ls = self.learner.stats()
                self.state["learner"] = ls
                for k in ("updates_per_transition", "update_ms_mean", "lag_updates",
                          "collector_wait_s", "collector_wait_timeouts"):
                    if ls[k] is not None:
                        self.model.logger.record(f"learner/{k}", ls[k])
            self.model.logger.dump(step=n)
            self.write_status("running")

    def _end_episode(self, t) -> None:
        ep, st = self._ep, self.state
        st["episodes"] += 1
        st["last_episode_id"] = t.episode
        st["recent_finishes"] = (st["recent_finishes"] + [t.status == rw.FINISHED])[-50:]
        status = t.status
        if status == rw.FINISHED:
            st["finishes"] += 1
            if st["best_finish_ms"] is None or t.race_ms < st["best_finish_ms"]:
                st["best_finish_ms"] = t.race_ms
                self._record = {"finish_ms": t.race_ms, "episode": t.episode}
        elif status == rw.ABANDONED:
            st["abandons"] += 1
        elif status == rw.TIME_LIMIT:
            st["time_limits"] += 1
        comps = ep["components"]
        ret = rw.discounted_return([rw.RewardBreakdown(**c) for c in comps]) if comps else None
        sums = {k: math.fsum(c[k] for c in comps) for k in ("progress", "time", "finish", "lap")}
        lat = ep["latency"]
        wall = time.monotonic() - ep["t0"]
        n = max(ep["steps"], 1)
        rec = {"episode": t.episode, "status": status, "valid_episode": t.valid,
               "race_ms": t.race_ms, "finish_ms": t.race_ms if status == rw.FINISHED else None,
               "transitions": ep["steps"], "valid_transitions": ep["valid"],
               "progress_max": ep["progress_max"], "return": ret, "reward_sums": sums,
               "wall_s": wall, "transitions_per_wall_s": ep["steps"] / wall if wall > 0 else None,
               "latency_ms_median": statistics.median(lat) if lat else None,
               "latency_ms_p95": _pct(lat, 0.95), "latency_ms_max": max(lat) if lat else None,
               "action_share": {k: c / n for k, c in zip(("coast", "gas", "brake", "gas_brake"),
                                                          ep["action_counts"])},
               "steer_abs_mean": ep["steer_abs_sum"] / n,
               "air_steps": ep["air_steps"], "air_brake_steps": ep["air_brake"],
               "burst_steps": self._burst_delta(),
               "error": None if t.valid else t.info.get("error"),
               "timesteps": (self.model.num_timesteps + 1) if self.model else None,
               "wall_time": time.strftime("%Y-%m-%dT%H:%M:%S")}
        self.episodes_w.write(rec)
        if self.model is not None:
            lg = self.model.logger
            lg.record("episode/progress_max", ep["progress_max"])
            lg.record("episode/transitions", ep["steps"])
            if ret is not None and t.valid:     # invalid episodes (protocol errors) would
                lg.record("episode/return", ret)  # plot as fake near-zero returns
                for k, v in sums.items():
                    lg.record(f"reward/{k}_sum", v)
            for k, v in rec["action_share"].items():
                lg.record(f"actions/share_{k}", v)
            lg.record("actions/steer_abs_mean", rec["steer_abs_mean"])
            if ep["air_steps"]:
                lg.record("actions/air_brake_share", ep["air_brake"] / ep["air_steps"])
            lg.record("exploration/burst_steps", rec["burst_steps"])
            lg.record("episode/finished", float(status == rw.FINISHED))
            lg.record("episode/finish_rate_50", sum(st["recent_finishes"]) / len(st["recent_finishes"]))
            lg.record("episode/finish_window_size", len(st["recent_finishes"]))
            lg.record("episode/abandoned", float(status == rw.ABANDONED))
            lg.record("episode/time_limit", float(status == rw.TIME_LIMIT))
            lg.record("episode/invalid", float(not t.valid))
            if status == rw.FINISHED:
                lg.record("episode/finish_s", t.race_ms / 1000.0)
                quiet = ep["air_brake"] <= 0.05 * ep["air_steps"]
                lg.record(f"episode/finish_s_{'no' if quiet else 'with'}_air_brake", t.race_ms / 1000.0)
            if st["best_finish_ms"] is not None:
                lg.record("totals/best_finish_s", st["best_finish_ms"] / 1000.0)
            lg.record("totals/episodes", st["episodes"])
            lg.record("totals/finishes", st["finishes"])
            lg.record("totals/invalid_transitions", st["invalid_transitions"])
            lg.record("totals/sim_hours", st["sim_ms"] / 3.6e6)
            if rec["transitions_per_wall_s"]:
                lg.record("throughput/transitions_per_wall_s", rec["transitions_per_wall_s"])
            if lat:
                lg.record("latency/median_ms", rec["latency_ms_median"])
                lg.record("latency/p95_ms", rec["latency_ms_p95"])
        self._ep = self._new_episode()
        self.write_status("running")

    # ---------------------------------------------------------------- checkpoints
    def save_checkpoint(self, tag: str | None = None) -> pathlib.Path:
        n = self.model.num_timesteps
        root = self.run_dir / "checkpoints"
        name = tag or f"{n:08d}"
        if pathlib.Path(name).name != name:
            raise ValueError("checkpoint tag must be a directory name")
        final = root / name
        if final.exists():
            final = root / f"{name}-{uuid.uuid4().hex[:12]}"
        d = root / f".pending-{uuid.uuid4().hex}"
        d.mkdir(parents=True)
        t0 = time.monotonic()
        # async learner: no gradient step in flight while weights and buffer are written
        with (self.learner.paused() if self.learner else contextlib.nullcontext()):
            self.model.save(d / "model.zip", exclude=["after_store"])
            self.model.save_replay_buffer(d / "replay_buffer.pkl")
            with open(d / "rng_state.pkl", "wb") as f:
                pickle.dump(self._rng_state(), f)
            updates = int(self.model._n_updates)
        env = self.handle.env
        state = {"schema": TRAINER_SCHEMA, "timesteps": n,
                 "replay_buffer_size": self.model.replay_buffer.size(),
                 "gradient_updates": updates,
                 "learner": self.derived["learner"],
                 "action_codec": self.codec.describe(),
                 "observation_normalization_sha256": env.encoder.norm["sha256"],
                 "map_uid": env.map_uid, "env": env.describe(), "config": self.cfg,
                 "derived": self.derived, "counters": {**self.state, "wall_s_before":
                                                       self.state["wall_s_before"] + time.monotonic() - self._t_start},
                 "restored_on_resume": ["policy and critic weights", "target critics",
                                        "actor, critic and entropy optimizers",
                                        "entropy coefficient", "replay buffer", "timestep counter",
                                        "trainer counters", "episode id",
                                        "random generator states (python, numpy, torch, action space)"],
                 "not_restored": ["partial episode in progress at the checkpoint",
                                  "game simulation state (a resume starts from the normal start)"]}
        _write_json_atomic(d / "trainer_state.json", state)
        # Publish only complete snapshots. A failed write leaves a diagnostic .pending
        # directory, never a partially overwritten checkpoint or a broken latest pointer.
        for file in d.iterdir():
            with file.open("rb") as handle:
                os.fsync(handle.fileno())
        d.rename(final)
        d = final
        self.state["checkpoints"].append({"dir": str(d.relative_to(self.run_dir)), "timesteps": n,
                                          "save_s": round(time.monotonic() - t0, 3)})
        # Preserve earlier complete checkpoints. Never remove a user's replay buffer
        # as a side effect of saving a newer checkpoint.
        _write_json_atomic(self.run_dir / "checkpoints" / "latest.json", self.state["checkpoints"][-1])
        self._last_ckpt_at = n
        self.write_status("running")
        return d

    def save_record(self) -> pathlib.Path:
        """Policy snapshot of a new best training finish: model.zip + trainer_state.json, no
        replay buffer. Evaluable (`tm.py eval --checkpoint best`), not resumable; latest.json
        and the periodic checkpoints are untouched. The time was driven by the stochastic
        training policy: the frozen policy must be evaluated to know its own time."""
        rec, self._record = self._record, None
        n = self.model.num_timesteps
        root = self.run_dir / "checkpoints"
        final = root / f"best-{rec['finish_ms']:06d}ms-{n:08d}"
        d = root / f".pending-{uuid.uuid4().hex}"
        d.mkdir(parents=True)
        with (self.learner.paused() if self.learner else contextlib.nullcontext()):
            self.model.save(d / "model.zip", exclude=["after_store"])
        env = self.handle.env
        _write_json_atomic(d / "trainer_state.json", {
            "schema": TRAINER_SCHEMA, "kind": "record", "timesteps": n, **rec,
            "action_codec": self.codec.describe(),
            "observation_normalization_sha256": env.encoder.norm["sha256"],
            "map_uid": env.map_uid, "config": self.cfg, "derived": self.derived})
        with (d / "model.zip").open("rb") as handle:
            os.fsync(handle.fileno())
        d.rename(final)
        info = {"dir": str(final.relative_to(self.run_dir)), "timesteps": n, **rec}
        _write_json_atomic(root / "best.json", info)
        self.incident("record", info)
        return final

    def _rng_state(self) -> dict:
        import random
        import torch
        return {"python": random.getstate(), "numpy": np.random.get_state(),
                "torch": torch.get_rng_state(),
                "action_space": self.model.action_space.np_random.bit_generator.state}

    def _restore_rng(self, path: pathlib.Path) -> bool:
        """Restore generators saved with the checkpoint. Older checkpoints have none."""
        if not path.exists():
            return False
        import random
        import torch
        with open(path, "rb") as f:
            s = pickle.load(f)
        random.setstate(s["python"])
        np.random.set_state(s["numpy"])
        torch.set_rng_state(s["torch"])
        self.model.action_space.np_random.bit_generator.state = s["action_space"]
        return True

    def after_store(self, dones, infos, stored: bool) -> None:
        n = self.model.num_timesteps
        done = bool(dones[0])
        saved = False
        if done and self._record is not None:
            self.save_record()
            saved = True
        if done and n - self._last_ckpt_at >= self.ckpt_every and (self.budget is None or n < self.budget):
            self.save_checkpoint()
            saved = True
        if saved:
            self.deterministic_eval()
            # the game waits for the first action of the auto-reset episode; start a fresh
            # one instead of risking the plugin's action timeout during the save
            self.model._last_obs = self.model.env.reset()
            self.model._last_original_obs = self.model._last_obs
        if not self.stop_requested and (self.run_dir / "STOP").exists():
            self.stop_requested, self.stop_reason = True, "stop_file"
        if self.stop_requested:
            raise StopTraining(self.stop_reason)
        if self.learner is not None:
            # sync: run the due gradient steps; async: bounded wait (< bridge action timeout)
            # only if the learner thread is too far behind
            self.learner.throttle()

    def _burst_delta(self) -> int:
        """Exploration burst steps since the previous episode end (bursts are counted per run session)."""
        now = getattr(self.model, "_burst_steps", 0)
        delta, self._burst_mark = now - getattr(self, "_burst_mark", 0), now
        return max(0, delta)

    def deterministic_eval(self, max_steps: int = 5000) -> None:
        """One deterministic episode of the current policy after each checkpoint, off the
        replay (not stored, no bursts), logged as eval/* in TensorBoard and det_evals.jsonl.
        Training curves are stochastic; this one is the frozen-policy time (sync speed)."""
        env, n = self.handle.env, self.model.num_timesteps
        rec = {"timesteps": n, "wall": time.strftime("%Y-%m-%dT%H:%M:%S")}
        try:
            obs, info = env.reset()
            air, air_steps, air_brake = False, 0, 0
            for _ in range(max_steps):
                act, _ = self.model.predict(np.asarray(obs, np.float32), deterministic=True)
                a = self.codec.decode(np.asarray(act, np.float64).reshape(-1))
                air_steps += air
                air_brake += air and a.brake
                t = env.step(a)
                air = _airborne(env.last_state)
                obs = t.next_obs
                if t.done:
                    break
            rec.update(episode=info.get("episode"), status=t.status, valid=t.valid, race_ms=t.race_ms,
                       progress=t.info.get("progress"), air_steps=air_steps, air_brake_steps=air_brake)
        except Exception as exc:     # never kill the run for a diagnostic episode
            self.incident("deterministic_eval_failed", {"error": repr(exc)})
            return
        with open(self.run_dir / "det_evals.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
        lg = self.model.logger
        lg.record("eval/finished", float(rec["status"] == rw.FINISHED))
        if rec["status"] == rw.FINISHED:
            lg.record("eval/finish_s", rec["race_ms"] / 1000.0)
        if rec["progress"] is not None:
            lg.record("eval/progress", rec["progress"])
        if air_steps:
            lg.record("eval/air_brake_share", air_brake / air_steps)
        lg.dump(step=n)

    # ---------------------------------------------------------------- run
    def _handle_sigint(self, signum, frame):
        if self.stop_requested:
            raise KeyboardInterrupt
        self.stop_requested, self.stop_reason = True, "sigint"
        print("\nstop requested: finishing the current transition, then saving "
              "(Ctrl+C again to abort without saving)", flush=True)

    def build_model(self, vec_env):
        if self.handle.env.observation_contract != self.derived["observation"]:
            raise ValueError("environment observation schema differs from training config")
        model_class, policy = model_class_for(self.cfg)
        s = dict(self.cfg["sac"])
        s.pop("hybrid_critic", None)
        net = s.pop("net_arch", [256, 256])
        lc = self.learner_cfg
        if lc is not None:        # learner section replaces SB3's own schedule: SB3 only
            s["train_freq"], s["gradient_steps"] = 1, 0     # collects; self.learner trains
        gamma = self.derived["gamma_per_step"]
        if "gamma" in s:
            raise ValueError("sac.gamma is derived from the reward discount; do not set it")
        tb = str(self.run_dir / "sb3")
        if self.resume:
            latest = json.loads((self.run_dir / "checkpoints" / "latest.json").read_text())
            d = self.run_dir / latest["dir"]
            model = model_class.load(d / "model.zip", env=vec_env, device="cpu")
            model.load_replay_buffer(d / "replay_buffer.pkl")
            ts = json.loads((d / "trainer_state.json").read_text())
            if ts["observation_normalization_sha256"] != self.handle.env.encoder.norm["sha256"]:
                raise ValueError("normalization differs from the checkpoint's")
            if ts["action_codec"]["name"] != self.codec.name:
                raise ValueError("action codec differs from the checkpoint's")
            c = ts["counters"]
            self.state.update({k: c[k] for k in self.state if k in c})
            if not self.state["checkpoints"] or self.state["checkpoints"][-1]["dir"] != latest["dir"]:
                self.state["checkpoints"].append(latest)   # saved before its own entry was added
            self._last_ckpt_at = model.num_timesteps
            self._rng_path = d / "rng_state.pkl"
            self.incident("resume", {"checkpoint": latest["dir"], "timesteps": model.num_timesteps,
                                     "replay_buffer_size": model.replay_buffer.size(),
                                     "rng_state_available": self._rng_path.exists()})
        elif "init_from" in self.cfg:
            model = self._init_from(model_class, vec_env, gamma, policy, s, net)
        else:
            model = model_class(policy, vec_env, gamma=gamma, seed=int(self.cfg["seed"]),
                                policy_kwargs={"net_arch": list(net)}, device="cpu", verbose=0,
                                **s)
        # one CSV per session: SB3 opens progress.csv in "w" mode, which would erase the
        # history on resume; TensorBoard appends a new event file by itself
        from stable_baselines3.common.logger import CSVOutputFormat, TensorBoardOutputFormat
        pathlib.Path(tb).mkdir(parents=True, exist_ok=True)
        csv_name = f"progress_{time.strftime('%Y%m%d-%H%M%S')}.csv" if self.resume else "progress.csv"
        model.set_logger(LockedLogger(tb, [CSVOutputFormat(str(pathlib.Path(tb) / csv_name)),
                                           TensorBoardOutputFormat(tb)]))
        if lc is not None:     # the schedule comes from the run config, including init_from
            model.gradient_steps = 0
            model.train_freq = 1
            model._convert_train_freq()
        model.after_store = self.after_store
        model._command_bursts = self.cfg.get("exploration", {}).get("command_bursts")
        diagnostic = self.cfg.get("critic_diagnostics", {})
        model._critic_diagnostics_every = diagnostic.get("every_updates", 0)
        model._critic_probe_size = diagnostic.get("samples", 2048)
        model._critic_reward_config = rw.RewardConfig(**self.cfg.get("reward", {})).__dict__
        model._critic_step_s = self.derived["step_s"]
        return model

    def _init_from(self, model_class, vec_env, gamma, policy, sac_args, net):
        """New run starting from another run's checkpoint: weights, target critics, optimizers,
        entropy coefficients and replay buffer, with this config's discount. Stored rewards do
        not depend on the discount, so the buffer stays valid when every other reward term is
        unchanged (checked). Explicit observation_v2 migration keeps network weights but
        starts fresh optimizers and replay. Counters and timesteps restart at 0."""
        d = init_checkpoint_dir(self.cfg)
        ts = json.loads((d / "trainer_state.json").read_text())
        if ts["observation_normalization_sha256"] != self.handle.env.encoder.norm["sha256"]:
            raise ValueError("init_from: normalization differs from the checkpoint's")
        if ts["action_codec"]["name"] != self.codec.name:
            raise ValueError("init_from: action codec differs from the checkpoint's")
        if ts["map_uid"] != self.handle.env.map_uid:
            raise ValueError("init_from: map differs from the checkpoint's")
        if ts["action_codec"]["ticks"] != self.codec.ticks:
            raise ValueError("init_from: action duration differs from the checkpoint's")
        if ts["config"]["sac"].get("hybrid_critic", "action_input") != self.cfg["sac"].get("hybrid_critic", "action_input"):
            raise ValueError("init_from: critic architecture differs from the checkpoint's")
        skip = ("discount_per_second", "sha256")
        old, new = ({k: v for k, v in r.items() if k not in skip}
                    for r in (ts["derived"]["reward"], self.derived["reward"]))
        migration = self.cfg["init_from"].get("migration")
        if old != new and migration not in ("fresh_replay", "observation_v2", "observation_v3"):
            raise ValueError("init_from: reward terms other than the discount differ; "
                             "the stored rewards would not match (use migration fresh_replay)")
        old_schema = ts["config"].get("observation_schema", SCHEMA_VERSION)
        new_schema = self.cfg.get("observation_schema", SCHEMA_VERSION)
        if migration in ("observation_v2", "observation_v3"):
            pair = ((SCHEMA_VERSION, EPISODE_SCHEMA_VERSION) if migration == "observation_v2"
                    else (EPISODE_SCHEMA_VERSION, LOOKAHEAD_SCHEMA_VERSION))
            if (old_schema, new_schema) != pair:
                raise ValueError(f"init_from: {migration} migration requires {pair[0]} -> {pair[1]}")
            from .checkpoint_migration import expand_observation_inputs
            source = model_class.load(d / "model.zip", device="cpu")
            model = model_class(policy, vec_env, gamma=gamma, seed=int(self.cfg["seed"]),
                                policy_kwargs={"net_arch": list(net)}, device="cpu", verbose=0,
                                **sac_args)
            if (getattr(source, "hybrid_target_entropy", None) !=
                    getattr(model, "hybrid_target_entropy", None)):
                raise ValueError("init_from: entropy targets differ during observation migration")
            base = observation_contract(old_schema)["dim"]
            detail = expand_observation_inputs(source, model, base_dim=base,
                                               extra=observation_contract(new_schema)["dim"] - base,
                                               mode=migration)
            # Fill the fresh replay using the loaded actor before the first update.
            model.learning_starts = max(model.learning_starts, model.batch_size)
            self.incident("init_from", {"checkpoint": str(d), "source_timesteps": ts["timesteps"],
                                      "source_gamma": source.gamma, "gamma": gamma,
                                      "learning_rate": model.learning_rate,
                                      "replay_buffer_size": 0, "buffer_capacity": model.buffer_size,
                                      "learning_starts": model.learning_starts,
                                      "use_loaded_policy": model._use_loaded_policy,
                                      "migration": detail})
            return model
        if old_schema != new_schema:
            raise ValueError("init_from: observation schemas differ; use explicit observation_v2 migration")
        # learning_rate and buffer_size come from this config (J4-13): the loaded optimizer
        # states keep their old lr, SB3 applies the new schedule at the first gradient step
        # J6-v12: the entropy targets too, else a checkpoint's targets silently override the config
        over = {k: self.cfg["sac"][k] for k in ("learning_rate", "buffer_size", "hybrid_target_entropy")
                if k in self.cfg["sac"]}
        model = model_class.load(d / "model.zip", env=vec_env, device="cpu", gamma=gamma, **over)
        trained = model._n_updates > 0
        old_steps = model.num_timesteps
        old_learning_starts = model.learning_starts
        model._use_loaded_policy = trained
        if migration == "fresh_replay":
            # New reward: old stored rewards are meaningless. Keep weights, optimizers and
            # temperatures; collect a fresh replay with the loaded actor before any update.
            model.learning_starts = max(int(self.cfg["sac"].get("learning_starts", 0)),
                                        model.batch_size)
            model.num_timesteps = 0
            self.incident("init_from", {"checkpoint": str(d), "source_timesteps": ts["timesteps"],
                                        "source_gamma": ts["derived"]["gamma_per_step"],
                                        "gamma": gamma, "learning_rate": model.learning_rate,
                                        "source_reward": ts["derived"]["reward"],
                                        "replay_buffer_size": 0,
                                        "buffer_capacity": model.replay_buffer.buffer_size,
                                        "learning_starts": model.learning_starts,
                                        "use_loaded_policy": model._use_loaded_policy,
                                        "hybrid_target_entropy": getattr(model, "hybrid_target_entropy", None),
                                        "migration": migration})
            return model
        from stable_baselines3.common.save_util import load_from_pkl
        source = load_from_pkl(d / "replay_buffer.pkl")
        copy_replay_buffer(source, model.replay_buffer)
        if trained and model.replay_buffer.size() >= model.batch_size:
            model.learning_starts = 0
        else:
            model.learning_starts = max(0, old_learning_starts - old_steps,
                                        model.batch_size - model.replay_buffer.size())
        model.num_timesteps = 0          # this run's budget and counters start here
        self.incident("init_from", {"checkpoint": str(d), "source_timesteps": ts["timesteps"],
                                    "source_gamma": ts["derived"]["gamma_per_step"],
                                    "gamma": gamma, "learning_rate": model.learning_rate,
                                    "source_buffer_capacity": source.buffer_size,
                                    "buffer_capacity": model.replay_buffer.buffer_size,
                                    "replay_buffer_size": model.replay_buffer.size(),
                                    "learning_starts": model.learning_starts,
                                    "hybrid_target_entropy": getattr(model, "hybrid_target_entropy", None),
                                    "use_loaded_policy": model._use_loaded_policy})
        return model

    def run(self) -> dict:
        from stable_baselines3.common.vec_env import DummyVecEnv
        import torch
        torch.set_num_threads(int(self.cfg.get("torch_threads", 4)))
        self._open_files()
        self.model = None
        stale = self.run_dir / "STOP"
        if stale.exists():   # a STOP left from a previous session must not end this one
            stale.rename(self.run_dir / f"STOP.stale.{int(time.time())}")
        if not self.resume:
            if "init_from" in self.cfg:     # record the checkpoint actually used, not "latest"
                self.cfg["init_from"]["checkpoint"] = init_checkpoint_dir(self.cfg).name
            _write_json_atomic(self.run_dir / "config.json",
                               {"config": self.cfg, "derived": self.derived})
        first_episode = int(self.cfg.get("first_episode", 1))
        if self.resume:
            prev = json.loads((self.run_dir / "status.json").read_text())
            first_episode = int(prev.get("last_episode_id", 0)) + 2
        self.handle = self.env_factory(first_episode)
        versions = {"libraries": library_versions(), "environment": self.handle.env.describe(),
                    "action_codec": self.codec.describe(), "env_factory": self.handle.info,
                    **self.extra_versions}
        _write_json_atomic(self.run_dir / ("versions_resume_%d.json" % int(time.time())
                                           if self.resume else "versions.json"), versions)
        gym_env = TrackmaniaGymEnv(self.handle.env, self.codec, recover=self.handle.recover,
                                   on_transition=self.on_transition, on_incident=self.incident)
        vec_env = DummyVecEnv([lambda: gym_env])
        old = signal.getsignal(signal.SIGINT)
        if self.install_signal_handler:
            signal.signal(signal.SIGINT, self._handle_sigint)
        phase, err = "finished_budget", None
        try:
            self.model = self.build_model(vec_env)
            if self.resume:   # after load: SB3 reseeds every generator while loading
                self._restore_rng(self._rng_path)
            self._window = (time.monotonic(), self.model.num_timesteps)
            remaining = None if self.budget is None else self.budget - self.model.num_timesteps
            if remaining is not None and remaining <= 0:
                phase = "finished_budget"
            else:
                if self.learner_cfg is not None:
                    self.learner = make_learner(self.model, self.learner_cfg)
                    self.learner.start()
                    self.incident("learner_start", {"learner": self.learner_cfg})
                self.write_status("running")
                if remaining is None:
                    # SB3 needs a finite target per learn() call. Continue in chunks;
                    # reset_num_timesteps=False keeps the model and replay buffer live.
                    while True:
                        self.model.learn(total_timesteps=self.ckpt_every, log_interval=1,
                                         reset_num_timesteps=False, progress_bar=False)
                        if self.learner is not None:
                            self.learner.check()
                else:
                    self.model.learn(total_timesteps=remaining, log_interval=1,
                                     reset_num_timesteps=not self.resume, progress_bar=False)
                    if self.learner is not None:
                        self.learner.check()
        except StopTraining as exc:
            phase, self.stop_reason = "stopped", str(exc)
        except KeyboardInterrupt:
            phase, self.stop_reason = "aborted", "second_sigint"
        except Exception as exc:     # the run records its own crash before re-raising
            phase, err = "crashed", f"{type(exc).__name__}: {exc}"
            self.stop_reason = err
            if isinstance(exc, FloatingPointError) or isinstance(exc.__cause__, FloatingPointError):
                phase = "diverged"   # weights are garbage: keep latest.json on the last sane save
        finally:
            if self.install_signal_handler:
                signal.signal(signal.SIGINT, old)
            try:
                if self.learner is not None:
                    self.learner.stop()
                    self.state["learner"] = self.learner.stats()
                    self.incident("learner_stop", self.state["learner"])
                if self.model is not None and phase not in ("aborted", "diverged"):
                    self.save_checkpoint()
            finally:
                self.handle.close()
                if self.model is not None:
                    self.incident("end", {"phase": phase, "reason": self.stop_reason})
                self.write_status(phase)
                stop = self.run_dir / "STOP"
                if stop.exists():
                    stop.rename(self.run_dir / f"STOP.consumed.{int(time.time())}")
                if self.model is not None:
                    self.model.logger.close()
                self._close_files()
        if err:
            raise RuntimeError(err)
        return json.loads((self.run_dir / "status.json").read_text())
