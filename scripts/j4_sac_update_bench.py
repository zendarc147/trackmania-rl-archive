"""Off-game benchmark of one SAC gradient step on CPU (J4, D21), with the J4 network and batch.

Fills an SB3 replay buffer with RANDOM SYNTHETIC data of the right shapes (25 observations,
3 or 5 actions), then times model.train(). This measures compute only; the game step time
comes from the throughput measurement (runs/j4/*-throughput).

Usage: uv run python scripts/j4_sac_update_bench.py [--threads 4] [--steps 500]
"""
from __future__ import annotations

import argparse
import json
import time

import gymnasium as gym
import numpy as np
import torch
from stable_baselines3 import SAC


class ShapeOnly(gym.Env):
    """SYNTHETIC env with the J4 spaces; never stepped by the benchmark."""

    def __init__(self, act_dim):
        self.observation_space = gym.spaces.Box(-5, 5, (25,), np.float32)
        self.action_space = gym.spaces.Box(-1, 1, (act_dim,), np.float32)

    def reset(self, *, seed=None, options=None):
        return np.zeros(25, np.float32), {}

    def step(self, a):
        return np.zeros(25, np.float32), 0.0, False, False, {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", type=int, default=4)
    ap.add_argument("--steps", type=int, default=500)
    a = ap.parse_args()
    torch.set_num_threads(a.threads)
    out = {"threads": a.threads, "torch": torch.__version__, "data": "random synthetic"}
    rng = np.random.default_rng(0)
    for act_dim in (3, 5):
        m = SAC("MlpPolicy", ShapeOnly(act_dim), policy_kwargs={"net_arch": [256, 256]},
                buffer_size=10000, batch_size=256, device="cpu", seed=0)
        for _ in range(5000):
            m.replay_buffer.add(rng.normal(size=(1, 25)).astype(np.float32),
                                rng.normal(size=(1, 25)).astype(np.float32),
                                rng.uniform(-1, 1, (1, act_dim)).astype(np.float32),
                                np.array([rng.normal()]), np.array([False]), [{}])
        m._setup_learn(1)
        m.train(gradient_steps=20, batch_size=256)       # warm-up
        t0 = time.perf_counter()
        m.train(gradient_steps=a.steps, batch_size=256)
        dt = (time.perf_counter() - t0) / a.steps * 1000
        obs = np.zeros(25, np.float32)
        t0 = time.perf_counter()
        for _ in range(1000):
            m.predict(obs, deterministic=True)
        pred = (time.perf_counter() - t0)
        out[f"act_dim_{act_dim}"] = {"ms_per_gradient_step": dt, "ms_per_predict": pred}
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
