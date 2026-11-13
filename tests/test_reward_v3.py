"""Off-game tests for reward/3 (lap-time term near the record, user request of 2026-10-01).

Scenarios using `SyntheticGame` are SYNTHETIC (invented 1-D physics, not TrackMania). The A01
ghost test reads the real reference run of the map profile; it checks the projection only,
not any driving performance.
"""
import json
import math
import pathlib
import unittest

from trackmania_rl import observation as obs
from trackmania_rl import reward as rw
from trackmania_rl.env import EnvUsageError, EpisodeRules, TrackmaniaEnv
from trackmania_rl.geometry import ProgressTracker, ReferenceLine
from trackmania_rl.training import load_config, validate_config

from test_env import BRAKE, COAST, GAS, LENGTH, NORM, PROFILE, SyntheticGame, run
from test_geometry import straight, synthetic_prepared

ROOT = pathlib.Path(__file__).resolve().parents[1]
V2 = rw.RewardConfig(progress_mode="delta", finish_bonus=20.0, discount_per_second=0.95)
V3 = rw.RewardConfig(progress_mode="delta", finish_bonus=20.0, discount_per_second=0.95,
                     lap_scale=12.5, lap_margin_s=0.25, target_time_s=8.0)
# SYNTHETIC ghost: constant pace along the straight line, 10 s reference run
GHOST = rw.LapGhost([0.0, LENGTH], [0.0, 10.0], LENGTH, 10.0)


def make_env(game=None, cfg=V3, ghost=GHOST):
    line = ReferenceLine(synthetic_prepared(straight(LENGTH)))
    env = TrackmaniaEnv(game or SyntheticGame(), PROFILE, obs.Encoder(NORM, PROFILE["uid"]),
                        ProgressTracker(line), cfg, EpisodeRules.from_profile(PROFILE),
                        ghost=ghost)
    return env


def ret(tr):
    return rw.discounted_return([rw.RewardBreakdown(**t.reward_components) for t in tr])


def lap_sum(tr):
    return sum(t.reward_components["lap"] for t in tr)


class RewardV3(unittest.TestCase):
    def test_old_hashes_unchanged_and_v3_is_a_new_schema(self):
        self.assertEqual(rw.RewardConfig().to_dict()["sha256"],
                         "7db1d3d8432464d38a294bd2384a05aa24d0f3e83752bbeb0557665c148588f3")
        # sha256 recorded by the reward/2 run a01-v4-obs2b
        self.assertEqual(V2.to_dict()["sha256"],
                         "f7808502e425e8bd56824c3f87113eb8f3a3accdf8aee19c86b1c201539dc112")
        self.assertEqual(V3.to_dict()["schema"], rw.REWARD_SCHEMA_V3)
        for bad in ({"lap_scale": 1.0, "target_time_s": 8.0},                     # potential mode
                    {"lap_scale": 1.0, "progress_mode": "delta"},                  # no target
                    {"lap_scale": 1.0, "progress_mode": "delta", "target_time_s": 8.0,
                     "lap_margin_s": 0.0}):
            with self.assertRaises(ValueError):
                rw.RewardConfig(**bad)
        # components of older runs (no "lap") still load
        self.assertEqual(rw.RewardBreakdown(1.0, -0.05, 0.0, 0.95, 0.99).lap, 0.0)

    def test_tenths_weigh_more_near_the_target(self):
        cfg = rw.RewardConfig(progress_mode="delta", lap_scale=12.5, lap_margin_s=0.25,
                              target_time_s=24.0)
        gain = lambda gap: cfg.lap_potential(24.0 + gap - 0.1) - cfg.lap_potential(24.0 + gap)
        self.assertAlmostEqual(gain(0.0), 5.0, places=6)
        self.assertAlmostEqual(gain(-1.0), 5.0, places=6)      # beating the record still pays
        self.assertLess(gain(6.0), 0.25)
        self.assertGreater(gain(0.1) / gain(6.0), 20.0)
        for g in (6.0, 1.0, 0.2, 0.0, -0.5):                     # monotone: faster is better
            self.assertGreater(gain(g), 0.0)

    def test_env_needs_a_ghost(self):
        with self.assertRaises(EnvUsageError):
            make_env(ghost=None)

    def test_finished_lap_pays_exactly_its_time(self):
        tr = run(make_env(), lambda i, e: GAS)
        self.assertEqual(tr[-1].status, rw.FINISHED)
        t_finish = tr[-1].race_ms / 1000.0
        self.assertAlmostEqual(tr[-1].info["eta_s"], t_finish)
        expected = V3.lap_potential(t_finish) - V3.lap_potential(V3.target_time_s)
        self.assertAlmostEqual(lap_sum(tr), expected, places=6)

    def test_faster_finish_is_preferred(self):
        fast = run(make_env(SyntheticGame(accel=10.0)), lambda i, e: GAS)
        slow = run(make_env(SyntheticGame(accel=6.0)), lambda i, e: GAS)
        self.assertLess(fast[-1].race_ms, slow[-1].race_ms)
        self.assertGreater(lap_sum(fast), lap_sum(slow))
        self.assertGreater(ret(fast), ret(slow))

    def test_abandon_never_beats_a_finish_within_the_limit(self):
        limit = PROFILE["episode"]["time_limit_ms"] / 1000.0
        worst_finish = V3.lap_potential(limit) - V3.lap_potential(V3.target_time_s)
        full = ret(run(make_env(), lambda i, e: GAS))
        for k in (0, 20, 60, 100):
            pol = lambda i, e, k=k: GAS if i < k else BRAKE if e.last_state["velocity"][2] > 0 else COAST
            tr = run(make_env(), pol)
            self.assertEqual(tr[-1].status, rw.ABANDONED, k)
            self.assertAlmostEqual(lap_sum(tr), worst_finish, places=6)
            self.assertLess(ret(tr), full, k)

    def test_abandon_charge_uses_the_later_of_eta_and_limit(self):
        b = rw.compute(V3, 0.5, 0.5, 0.05, rw.ABANDONED, prev_eta_s=70.0, next_eta_s=70.05,
                       time_limit_s=60.0)
        self.assertAlmostEqual(b.lap, V3.lap_potential(70.05) - V3.lap_potential(70.0))
        with self.assertRaises(ValueError):
            rw.compute(V3, 0.5, 0.5, 0.05, rw.ABANDONED, prev_eta_s=9.0, next_eta_s=9.05)
        with self.assertRaises(ValueError):
            rw.compute(V3, 0.5, 0.51, 0.05, rw.RUNNING)

    def test_back_and_forth_pays_nothing(self):
        # same race time, the car goes forward then back to the same place
        s = [100.0, 150.0, 200.0, 150.0, 100.0]
        etas = [GHOST.eta(V3, x, 5.0) for x in s]
        lap = sum(V3.lap_potential(b) - V3.lap_potential(a) for a, b in zip(etas, etas[1:]))
        self.assertAlmostEqual(lap, 0.0)
        pol = lambda i, e: GAS if (i // 40) % 2 == 0 else BRAKE
        self.assertLess(ret(run(make_env(), pol)), ret(run(make_env(), lambda i, e: GAS)))

    def test_driving_beats_stopping(self):
        stop = ret(run(make_env(), lambda i, e: COAST))
        for accel in (0.6, 8.0):
            drive = ret(run(make_env(SyntheticGame(accel=accel)), lambda i, e: GAS))
            self.assertGreater(drive, stop, accel)

    def test_a01_ghost_from_the_real_reference(self):
        from trackmania_rl.runtime import lap_ghost, load_map_assets
        cfg = load_config(ROOT / "configs/training/a01_sac_hybrid4_v5_lap.json")
        validate_config(cfg)
        rc = rw.RewardConfig(**cfg["reward"])
        g = lap_ghost(load_map_assets(cfg["map"]))
        self.assertAlmostEqual(g.eta(rc, 0.0, 0.0), rc.target_time_s)
        self.assertAlmostEqual(g.tau(g.length), 27.11)
        # driving exactly like the 27.11 s reference keeps eta on the way to 27.11
        for s in (300.0, 1000.0, 1800.0, g.length):
            eta = g.eta(rc, s, g.tau(s))
            self.assertTrue(rc.target_time_s - 1e-9 <= eta <= 27.11 + 1e-9, s)
        self.assertTrue(all(b > a for a, b in zip(g.s, g.s[1:])))
        self.assertEqual(cfg["init_from"]["migration"], "fresh_replay")


if __name__ == "__main__":
    unittest.main()
