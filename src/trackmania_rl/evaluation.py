"""Frozen-policy evaluator (J4). Separate from training: no learning, no replay buffer.

- Policy: SB3 SAC actor loaded from a checkpoint's model.zip, deterministic actions (the mean
  of the squashed Gaussian), weights never updated.
- Normalization: the checkpoint's trainer_state.json names the normalization hash; the map
  profile's normalization must match it, otherwise the evaluation refuses to start.
- Episodes from the normal start (reset by the environment), full races, game race time.
- Modes: "sync" (the game waits for each action, D20) and "realtime" (the game never waits;
  decision latency is measured and late boundaries are accepted up to a bound).
- Speed must be 1 for any result compared with a leaderboard (D34); faster speeds are allowed
  only for diagnostics and are recorded as such.
Limit (J3-03): with the controlled-finish mechanism of bridge >= 0.2.1 the game does not
validate the run (no official time, no replay). The race time reported is the game's
RaceTime at the finish, confirmed by RaceFinished and all checkpoints.
"""
from __future__ import annotations

import json
import pathlib
import statistics
import time

import numpy as np

from . import reward as rw
from .actions import make_codec
from .bridge import BridgeError

EVAL_SCHEMA = "trackmania_rl.evaluation/1"


def load_policy(checkpoint_dir: pathlib.Path):
    from stable_baselines3 import SAC
    ts = json.loads((checkpoint_dir / "trainer_state.json").read_text())
    if ts["action_codec"]["name"] == "hybrid4_v1":
        from .training import model_class_for
        model_class = model_class_for(ts["config"])[0]   # HybridSAC or HybridQ4SAC
    else:
        model_class = SAC
    model = model_class.load(checkpoint_dir / "model.zip", device="cpu")
    model.policy.set_training_mode(False)
    return model, ts


def _pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * (len(xs) - 1)))] if xs else None


def evaluate(env, model, trainer_state: dict, *, episodes: int, out_dir: pathlib.Path,
             mode: str, speed: float, max_steps: int = 2000,
             official_finish: bool = False) -> dict:
    if env.encoder.norm["sha256"] != trainer_state["observation_normalization_sha256"]:
        raise ValueError("normalization of the map profile differs from the checkpoint's")
    from .observation import SCHEMA_VERSION
    schema = trainer_state["config"].get("observation_schema", SCHEMA_VERSION)
    if env.observation_schema != schema or model.observation_space.shape != (env.observation_contract["dim"],):
        raise ValueError("observation schema differs from the checkpoint's")
    codec = make_codec(trainer_state["action_codec"]["name"], trainer_state["action_codec"]["ticks"])
    out_dir.mkdir(parents=True, exist_ok=True)
    ep_f = open(out_dir / "eval_episodes.jsonl", "w", encoding="utf-8")
    tr_f = open(out_dir / "eval_transitions.jsonl", "w", encoding="utf-8")
    results = []
    try:
        for _ in range(episodes):
            obs, info = env.reset()
            steps, comps, decide_ms, lat_ms, lags = 0, [], [], [], []
            t = None
            while steps < max_steps:
                t0 = time.perf_counter()
                act, _ = model.predict(np.asarray(obs, np.float32), deterministic=True)
                action = codec.decode(act)
                decide_ms.append((time.perf_counter() - t0) * 1000)
                t = env.step(action)
                steps += 1
                state = env.last_state if t.valid else {}
                tr_f.write(json.dumps({"episode": t.episode, "action_id": t.action_id,
                                       "valid": t.valid, "status": t.status,
                                       "action": [action.steer, action.accelerate, action.brake],
                                       "race_ms": t.race_ms, "dt_ms": t.dt_ms,
                                       "progress": t.info.get("progress"),
                                       "lateral_m": t.info.get("lateral_m"),
                                       "vertical_m": t.info.get("vertical_m"),
                                       "display_speed": state.get("display_speed"),
                                       "gear": state.get("gear"),
                                       "wheel_contact": state.get("wheel_contact"),
                                       "wheel_sliding": state.get("wheel_sliding"),
                                       "applied_inputs": state.get("inputs"),
                                       "same_tick_finish": t.info.get("same_tick_finish", False),
                                       "finish_before_action": t.info.get("finish_before_action", False),
                                       "decision_ms": round(decide_ms[-1], 4),
                                       "latency_ms": None if t.info.get("latency_s") is None
                                       else round(t.info["latency_s"] * 1000, 3),
                                       "error": t.info.get("error")}, separators=(",", ":")) + "\n")
                if t.valid:
                    comps.append(t.reward_components)
                    if t.info.get("latency_s") is not None:
                        lat_ms.append(t.info["latency_s"] * 1000)
                    if t.info.get("reason") == "boundary":
                        lags.append(t.dt_ms - env.action_ticks * env.tick_ms)
                    obs = t.next_obs
                if t.done:
                    break
            normal_dialog = False
            if official_finish and t and t.status == rw.FINISHED:
                try:
                    # The end dialog appears only if PreventSimulationFinish was not called.
                    event = env.bridge.wait_for(lambda m: m.get("event") == "game_state"
                                                and m.get("new_state") == 1024, 6.0)
                    normal_dialog = event is not None
                except BridgeError:
                    normal_dialog = False
            rec = {"episode": env.episode, "status": t.status if t else None,
                   "normal_finish_dialog_observed": normal_dialog,
                   "valid": bool(t and t.valid), "race_ms": t.race_ms if t else None,
                   "finish_ms": t.race_ms if t and t.status == rw.FINISHED else None,
                   "transitions": steps, "progress_max": env.tracker.max_s_m / env.tracker.line.length,
                   "return": rw.discounted_return([rw.RewardBreakdown(**c) for c in comps]) if comps else None,
                   "decision_ms_median": statistics.median(decide_ms) if decide_ms else None,
                   "decision_ms_p95": _pct(decide_ms, 0.95),
                   "decision_ms_max": max(decide_ms) if decide_ms else None,
                   "latency_ms_median": statistics.median(lat_ms) if lat_ms else None,
                   "latency_ms_p95": _pct(lat_ms, 0.95),
                   "late_boundaries": sum(1 for x in lags if x > 0),
                   "max_lag_ms": max(lags) if lags else None,
                   "error": None if not t or t.valid else t.info.get("error")}
            ep_f.write(json.dumps(rec) + "\n")
            ep_f.flush()
            results.append(rec)
            print(json.dumps({k: rec[k] for k in ("episode", "status", "race_ms", "progress_max",
                                                   "decision_ms_median", "late_boundaries")}), flush=True)
            if official_finish and t and t.status == rw.FINISHED:
                # Without prevention, TMNF cannot auto-reset after a finish.
                break
    finally:
        ep_f.close()
        tr_f.close()
    times = [r["finish_ms"] for r in results if r["finish_ms"] is not None]
    summary = {"schema": EVAL_SCHEMA, "mode": mode, "speed": speed,
               "requested_episodes": episodes, "official_finish_mode": official_finish,
               "normal_finish_dialogs_observed": sum(r["normal_finish_dialog_observed"] for r in results),
               "comparable_to_leaderboard": False,
               "comparable_note": "normal dialog alone does not prove an official recorded time; verify game record separately",
               "deterministic_policy": True, "episodes": len(results), "complete": len(results) == episodes,
               "finishes": len(times), "success_rate": len(times) / len(results) if results else None,
               "best_finish_ms": min(times) if times else None,
               "median_finish_ms": statistics.median(times) if times else None,
               "stdev_finish_ms": statistics.pstdev(times) if len(times) > 1 else None,
               "statuses": {s: sum(1 for r in results if r["status"] == s)
                            for s in {r["status"] for r in results}},
               "decision_ms_median": statistics.median([r["decision_ms_median"] for r in results
                                                        if r["decision_ms_median"] is not None] or [0]),
               "decision_ms_max": max([r["decision_ms_max"] or 0 for r in results] or [0]),
               "late_boundaries": sum(r["late_boundaries"] for r in results),
               "identical_runs": len({(r["status"], r["race_ms"], r["transitions"]) for r in results}) == 1}
    return summary
