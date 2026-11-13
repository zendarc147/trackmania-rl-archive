"""Off-game tests for the J4 learning loop (action codecs, gym adapter, SAC trainer, resume).

EVERY GAME IN THIS FILE IS SYNTHETIC (tests/test_env.SyntheticGame: an invented 1-D car that
speaks the bridge message format). These tests check plumbing: codecs, invalid-transition
filtering, checkpoints, stop and resume. They do not validate the game integration nor any
learning performance.
"""
import json
import pathlib
import tempfile
import unittest

import numpy as np

from trackmania_rl import actions
from trackmania_rl.gym_env import TrackmaniaGymEnv
from trackmania_rl.training import EnvHandle, Trainer, validate_config

from test_env import SyntheticGame, make_env

CFG = {"name": "synthetic_smoke", "map": "SYNTHETIC", "action_codec": "threshold_v1",
       "action_ticks": 5, "seed": 3, "torch_threads": 1,
       "budget": {"transitions": 400, "cap_transitions": 1000},
       "checkpoint_every_transitions": 150, "log_transitions": True,
       "sac": {"net_arch": [32, 32], "learning_starts": 50, "batch_size": 32,
               "buffer_size": 5000}}


def synthetic_factory(fault_at=None):
    """EnvHandle over a SYNTHETIC game. fault_at: set of global step indices that fail."""
    counter = {"n": 0}

    def factory(first_episode):
        env, game = make_env()
        env.episode = first_episode - 1
        orig = game.send_line

        def send_line(line):
            if line.startswith("A "):
                counter["n"] += 1
                if fault_at and counter["n"] in fault_at:
                    game.fault = "silence"
            return orig(line)

        game.send_line = send_line
        return EnvHandle(env=env, close=lambda: None, recover=None, info={"synthetic": True})
    return factory


class ActionCodecs(unittest.TestCase):
    def test_threshold(self):
        c = actions.make_codec("threshold_v1")
        a = c.decode([0.5, 0.1, -0.1])
        self.assertEqual((a.steer, a.accelerate, a.brake, a.ticks), (0.5, True, False, 5))
        self.assertEqual(c.decode([-2.0, -1, 1]).steer, -1.0)     # clipped, never out of range
        with self.assertRaises(ValueError):
            c.decode([0.0, float("nan"), 0.0])
        with self.assertRaises(ValueError):
            c.decode([0.0, 0.0])

    def test_argmax4_covers_the_four_combinations(self):
        c = actions.make_codec("argmax4_v1")
        seen = set()
        for k in range(4):
            v = [0.3, -1, -1, -1, -1]
            v[1 + k] = 1
            a = c.decode(v)
            seen.add((a.accelerate, a.brake))
            self.assertEqual(a.steer, 0.3)
        self.assertEqual(seen, set(actions.COMBOS))
        self.assertEqual(c.decode([0, 0.2, 0.2, 0, 0]).accelerate, False)   # tie: lowest index

    def test_unknown_codec(self):
        with self.assertRaises(ValueError):
            actions.make_codec("nope")


class GymAdapter(unittest.TestCase):
    def test_spaces_and_invalid_transition(self):
        env, game = make_env()
        g = TrackmaniaGymEnv(env, actions.make_codec("threshold_v1"))
        obs, info = g.reset()
        self.assertEqual(obs.shape, g.observation_space.shape)
        self.assertEqual(g.action_space.shape, (3,))
        o, r, term, trunc, info = g.step(np.array([0, 1, -1], np.float32))
        self.assertFalse(info["invalid"])
        game.fault = "silence"
        o, r, term, trunc, info = g.step(np.array([0, 1, -1], np.float32))
        self.assertTrue(info["invalid"])
        self.assertTrue(trunc and not term)       # ends the episode, never a terminal value


class BudgetConfig(unittest.TestCase):
    def test_cap_is_enforced(self):
        bad = json.loads(json.dumps(CFG))
        bad["budget"]["transitions"] = 2000
        with self.assertRaises(ValueError):
            validate_config(bad)

    def test_explicit_unlimited_budget_is_valid(self):
        cfg = json.loads(json.dumps(CFG))
        cfg["budget"]["transitions"] = None
        self.assertIs(validate_config(cfg), cfg)

    def test_unlimited_budget_requires_a_positive_checkpoint_interval(self):
        cfg = json.loads(json.dumps(CFG))
        cfg["budget"]["transitions"] = None
        cfg["checkpoint_every_transitions"] = 0
        with self.assertRaises(ValueError):
            validate_config(cfg)


class TrainerSmoke(unittest.TestCase):
    """SYNTHETIC: tiny SAC run, checkpoints, clean stop, resume."""

    def test_train_stop_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = pathlib.Path(tmp) / "run"
            cfg = json.loads(json.dumps(CFG))
            cfg["budget"]["transitions"] = 300
            st = Trainer(cfg, run, synthetic_factory(fault_at={120}),
                         install_signal_handler=False).run()
            self.assertEqual(st["phase"], "finished_budget")
            self.assertEqual(st["timesteps"], 300)
            self.assertEqual(st["invalid_transitions"], 1)
            ck = json.loads((run / "checkpoints" / "latest.json").read_text())
            state = json.loads((run / ck["dir"] / "trainer_state.json").read_text())
            # one invalid transition was dropped: buffer = timesteps - 1
            self.assertEqual(state["replay_buffer_size"], 299)
            for f in ("config.json", "versions.json", "status.json", "episodes.jsonl",
                      "transitions.jsonl", "incidents.jsonl", "sb3/progress.csv"):
                self.assertTrue((run / f).exists(), f)
            self.assertTrue(list((run / "sb3").glob("events.out.tfevents.*")))
            # one deterministic diagnostic episode per checkpoint, kept out of the replay
            evals = [json.loads(l) for l in (run / "det_evals.jsonl").read_text().splitlines()]
            self.assertTrue(evals and all("status" in e for e in evals))
            ep = json.loads((run / "episodes.jsonl").read_text().splitlines()[0])
            self.assertIn("air_brake_steps", ep)
            # all complete checkpoints remain available for an exact resume
            rbs = list((run / "checkpoints").glob("*/replay_buffer.pkl"))
            self.assertGreaterEqual(len(rbs), 1)

            # resume with a larger budget, then a clean stop through the STOP file
            cfg2 = json.loads((run / "config.json").read_text())["config"]
            cfg2["budget"]["transitions"] = 450
            tr = Trainer(cfg2, run, synthetic_factory(), resume=True, install_signal_handler=False)
            real_after = tr.after_store

            def after_store(dones, infos, stored):
                if tr.model.num_timesteps >= 360:
                    (run / "STOP").write_text("test")
                real_after(dones, infos, stored)
            tr.after_store = after_store
            st2 = tr.run()
            self.assertEqual(st2["phase"], "stopped")
            self.assertEqual(st2["stop_reason"], "stop_file")
            self.assertEqual(st2["timesteps"], 360)
            self.assertGreaterEqual(st2["episodes"], st["episodes"])   # counters restored, not 0
            self.assertGreater(st["episodes"], 0)
            ck2 = json.loads((run / "checkpoints" / "latest.json").read_text())
            s2 = json.loads((run / ck2["dir"] / "trainer_state.json").read_text())
            self.assertEqual(s2["replay_buffer_size"], 359)            # buffer restored + grown
            rbs = list((run / "checkpoints").glob("*/replay_buffer.pkl"))
            self.assertIn(ck2["dir"].split("/")[-1], [p.parent.name for p in rbs])
            kinds = [json.loads(line)["kind"] for line in (run / "incidents.jsonl").read_text().splitlines()]
            self.assertIn("resume", kinds)
            self.assertFalse((run / "STOP").exists())

    def test_unlimited_resume_crosses_chunks_and_stops_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = pathlib.Path(tmp) / "run"
            cfg = json.loads(json.dumps(CFG))
            cfg["budget"]["transitions"] = 60
            cfg["checkpoint_every_transitions"] = 20
            Trainer(cfg, run, synthetic_factory(), install_signal_handler=False).run()

            cfg["budget"]["transitions"] = None
            trainer = Trainer(cfg, run, synthetic_factory(), resume=True,
                              install_signal_handler=False)
            after_store = trainer.after_store

            def stop_after_multiple_chunks(dones, infos, stored):
                if trainer.model.num_timesteps >= 105:
                    (run / "STOP").write_text("test")
                after_store(dones, infos, stored)

            trainer.after_store = stop_after_multiple_chunks
            status = trainer.run()
            self.assertEqual(status["phase"], "stopped")
            self.assertEqual(status["stop_reason"], "stop_file")
            self.assertGreaterEqual(status["timesteps"], 105)
            self.assertIsNone(status["budget_transitions"])
            self.assertIsNone(status["budget_fraction"])
            self.assertIsNone(status["eta_hours"])
            latest = json.loads((run / "checkpoints/latest.json").read_text())
            self.assertEqual(latest["timesteps"], status["timesteps"])
            self.assertFalse((run / "STOP").exists())

    def test_failed_checkpoint_preserves_previous_complete_snapshot(self):
        from unittest.mock import patch
        import hashlib
        with tempfile.TemporaryDirectory() as tmp:
            run = pathlib.Path(tmp) / "run"
            cfg = json.loads(json.dumps(CFG))
            cfg["budget"]["transitions"] = 60
            trainer = Trainer(cfg, run, synthetic_factory(), install_signal_handler=False)
            trainer.run()
            latest = run / "checkpoints/latest.json"
            before = latest.read_bytes()
            checkpoint = run / json.loads(before)["dir"]
            hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                      for p in checkpoint.iterdir() if p.is_file()}

            def interrupted(path):
                pathlib.Path(path).write_bytes(b"interrupted replay write")
                raise OSError("synthetic disk failure")

            with patch.object(trainer.model, "save_replay_buffer", side_effect=interrupted):
                with self.assertRaisesRegex(OSError, "synthetic disk failure"):
                    trainer.save_checkpoint()
            self.assertEqual(latest.read_bytes(), before)
            self.assertEqual(hashes, {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in checkpoint.iterdir() if p.is_file()})

    def test_noop_resume_restores_random_generators(self):
        import random
        import torch
        with tempfile.TemporaryDirectory() as tmp:
            run = pathlib.Path(tmp) / "run"
            cfg = json.loads(json.dumps(CFG))
            cfg["budget"]["transitions"] = 60
            trainer = Trainer(cfg, run, synthetic_factory(), install_signal_handler=False)
            trainer.run()
            expected = (random.random(), np.random.rand(), torch.rand(3),
                        trainer.model.action_space.sample())
            resumed = Trainer(cfg, run, synthetic_factory(), resume=True,
                              install_signal_handler=False)
            resumed.run()
            actual = (random.random(), np.random.rand(), torch.rand(3),
                      resumed.model.action_space.sample())
            self.assertEqual(expected[:2], actual[:2])
            torch.testing.assert_close(expected[2], actual[2], rtol=0, atol=0)
            np.testing.assert_array_equal(expected[3], actual[3])

    def test_resume_restores_the_same_policy(self):
        from stable_baselines3 import SAC
        with tempfile.TemporaryDirectory() as tmp:
            run = pathlib.Path(tmp) / "run"
            cfg = json.loads(json.dumps(CFG))
            cfg["budget"]["transitions"] = 200
            tr = Trainer(cfg, run, synthetic_factory(), install_signal_handler=False)
            tr.run()
            ck = run / json.loads((run / "checkpoints" / "latest.json").read_text())["dir"]
            m = SAC.load(ck / "model.zip", device="cpu")
            x = np.linspace(-1, 1, 25, dtype=np.float32)
            a1, _ = tr.model.predict(x, deterministic=True)
            a2, _ = m.predict(x, deterministic=True)
            np.testing.assert_allclose(a1, a2, atol=1e-6)
            self.assertIsNotNone(m.ent_coef_optimizer)                 # optimizer state saved

    def test_hybrid_categorical_distribution_and_resume(self):
        import torch
        from trackmania_rl.evaluation import load_policy
        with tempfile.TemporaryDirectory() as tmp:
            cfg = json.loads(json.dumps(CFG))
            cfg["action_codec"] = "hybrid4_v1"
            cfg["budget"]["transitions"] = 70
            run = pathlib.Path(tmp) / "hybrid"
            status = Trainer(cfg, run, synthetic_factory(), install_signal_handler=False).run()
            self.assertEqual(status["phase"], "finished_budget")
            ck = run / json.loads((run / "checkpoints" / "latest.json").read_text())["dir"]
            model, state = load_policy(ck)
            self.assertEqual(state["action_codec"]["name"], "hybrid4_v1")
            obs = torch.zeros((2, 25), dtype=torch.float32)
            _, _, probs, log_probs, _ = model.actor.sample_heads(obs)
            torch.testing.assert_close(probs.sum(-1), torch.ones(2))
            self.assertTrue(torch.isfinite(log_probs).all())
            self.assertEqual(model.replay_buffer.size(), 0)  # evaluation loads no training data
            sampled = model.predict(np.zeros(25, np.float32), deterministic=True)[0]
            self.assertEqual(tuple(sorted(sampled[1:].tolist())), (-1.0, -1.0, -1.0, 1.0))
            self.assertEqual(actions.make_codec("hybrid4_v1").decode(sampled).ticks, 5)
            cfg["budget"]["transitions"] = 90
            resumed = Trainer(cfg, run, synthetic_factory(), resume=True,
                              install_signal_handler=False).run()
            self.assertEqual(resumed["timesteps"], 90)
            self.assertEqual(resumed["phase"], "finished_budget")


class RecordSnapshot(unittest.TestCase):
    """SYNTHETIC: every new best finish leaves an evaluable policy snapshot, nothing else."""

    def test_new_best_finish_saves_policy(self):
        from types import SimpleNamespace
        from trackmania_rl import reward as rw
        from trackmania_rl.evaluation import load_policy
        with tempfile.TemporaryDirectory() as tmp:
            run = pathlib.Path(tmp) / "run"
            cfg = json.loads(json.dumps(CFG))
            cfg["budget"]["transitions"] = 60
            tr = Trainer(cfg, run, synthetic_factory(), install_signal_handler=False)
            tr.run()
            latest = (run / "checkpoints" / "latest.json").read_text()
            tr._open_files()
            tr.state["best_finish_ms"] = None
            for ms in (31000, 32000, 29500):        # record, slower (no record), record
                tr._end_episode(SimpleNamespace(status=rw.FINISHED, race_ms=ms, episode=ms,
                                                valid=True, info={}))
                if tr._record is not None:
                    tr.save_record()
            tr._close_files()
            best = json.loads((run / "checkpoints" / "best.json").read_text())
            self.assertEqual(best["finish_ms"], 29500)
            self.assertEqual(len(list((run / "checkpoints").glob("best-*"))), 2)
            self.assertEqual((run / "checkpoints" / "latest.json").read_text(), latest)
            self.assertFalse((run / best["dir"] / "replay_buffer.pkl").exists())
            model, ts = load_policy(run / best["dir"])
            self.assertEqual(ts["kind"], "record")


class InitFrom(unittest.TestCase):
    """SYNTHETIC: a new run starts from another run's checkpoint with another discount."""

    def test_new_discount_keeps_weights_and_buffer(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = pathlib.Path(tmp) / "src"
            cfg = json.loads(json.dumps(CFG))
            cfg["budget"]["transitions"] = 120
            Trainer(cfg, src, synthetic_factory(), install_signal_handler=False).run()
            cfg2 = json.loads(json.dumps(cfg))
            cfg2["reward"] = {"discount_per_second": 0.95}
            cfg2["init_from"] = {"run": str(src), "checkpoint": "latest"}
            cfg2["budget"]["transitions"] = 60
            cfg2["sac"].update(buffer_size=8000, learning_rate=1e-4)   # J4-13 overrides
            dst = pathlib.Path(tmp) / "dst"
            st = Trainer(validate_config(cfg2), dst, synthetic_factory(),
                         install_signal_handler=False).run()
            self.assertEqual(st["timesteps"], 60)
            saved = json.loads((dst / "config.json").read_text())["config"]
            self.assertEqual(saved["init_from"]["checkpoint"], "00000120")   # "latest" resolved
            inc = [json.loads(line) for line in (dst / "incidents.jsonl").read_text().splitlines()]
            init = next(i for i in inc if i["kind"] == "init_from")
            self.assertAlmostEqual(init["gamma"], 0.95 ** 0.05)
            self.assertEqual(init["replay_buffer_size"], 120)
            self.assertEqual((init["source_buffer_capacity"], init["buffer_capacity"]), (5000, 8000))
            self.assertEqual(init["learning_rate"], 1e-4)
            ck = json.loads((dst / "checkpoints" / "latest.json").read_text())
            self.assertEqual(json.loads((dst / ck["dir"] / "trainer_state.json").read_text())
                             ["replay_buffer_size"], 180)
            from trackmania_rl.evaluation import load_policy
            loaded = load_policy(dst / ck["dir"])[0]
            self.assertAlmostEqual(loaded.gamma, 0.95 ** 0.05)
            self.assertEqual(loaded.critic.optimizer.param_groups[0]["lr"], 1e-4)   # applied, not only stored
            # another reward term would make the stored rewards wrong: refused
            cfg2["reward"] = {"discount_per_second": 0.95, "finish_bonus": 10.0}
            with self.assertRaises(RuntimeError):
                Trainer(cfg2, pathlib.Path(tmp) / "bad", synthetic_factory(),
                        install_signal_handler=False).run()
            # unless the replay restarts empty (reward/3 migration): weights kept, no old rewards
            cfg2["init_from"]["migration"] = "fresh_replay"
            fresh = pathlib.Path(tmp) / "fresh"
            st = Trainer(validate_config(cfg2), fresh, synthetic_factory(),
                         install_signal_handler=False).run()
            self.assertEqual(st["timesteps"], 60)
            inc = [json.loads(line) for line in (fresh / "incidents.jsonl").read_text().splitlines()]
            init = next(i for i in inc if i["kind"] == "init_from")
            self.assertEqual((init["replay_buffer_size"], init["migration"]), (0, "fresh_replay"))
            self.assertTrue(init["use_loaded_policy"])
            ck = json.loads((fresh / "checkpoints" / "latest.json").read_text())
            self.assertEqual(json.loads((fresh / ck["dir"] / "trainer_state.json").read_text())
                             ["replay_buffer_size"], 60)


class CopyReplayBuffer(unittest.TestCase):
    """SYNTHETIC buffers: chronological copy across a wrapped source, into larger and smaller targets."""

    def _buf(self, size):
        import gymnasium as gym
        from stable_baselines3.common.buffers import ReplayBuffer
        return ReplayBuffer(size, gym.spaces.Box(-1, 1, (2,)), gym.spaces.Box(-1, 1, (1,)))

    def test_wrapped_source_is_copied_oldest_first(self):
        from trackmania_rl.training import copy_replay_buffer
        src = self._buf(4)
        for i in range(6):      # wraps: holds 2, 3, 4, 5 with pos == 2
            src.add(np.full(2, i), np.full(2, i + 1), np.array([0.0]), np.array([i]),
                    np.array([False]), [{}])
        big = self._buf(10)
        copy_replay_buffer(src, big)
        self.assertEqual(big.size(), 4)
        self.assertEqual(big.rewards[:4, 0].tolist(), [2, 3, 4, 5])
        self.assertEqual(big.next_observations[:4, 0, 0].tolist(), [3, 4, 5, 6])
        small = self._buf(3)
        copy_replay_buffer(src, small)
        self.assertEqual((small.size(), small.pos, small.full), (3, 0, True))
        self.assertEqual(small.rewards[:, 0].tolist(), [3, 4, 5])


class Divergence(unittest.TestCase):
    """SYNTHETIC: a non-finite loss stops the run and never becomes the latest checkpoint."""

    def test_diverged_run_keeps_last_sane_checkpoint(self):
        from unittest import mock
        from stable_baselines3 import SAC
        real_train = SAC.train

        def train(self, gradient_steps, batch_size=64):
            if self.num_timesteps > 700:          # after a checkpoint (saved at episode ends)
                raise FloatingPointError("synthetic non-finite loss")
            return real_train(self, gradient_steps, batch_size)

        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(SAC, "train", train):
            run = pathlib.Path(tmp) / "run"
            cfg = json.loads(json.dumps(CFG))
            cfg["budget"]["transitions"] = 1000
            with self.assertRaises(RuntimeError):
                Trainer(cfg, run, synthetic_factory(),
                        install_signal_handler=False).run()
            st = json.loads((run / "status.json").read_text())
            self.assertEqual(st["phase"], "diverged")
            ck = json.loads((run / "checkpoints" / "latest.json").read_text())
            self.assertLessEqual(ck["timesteps"], 700)


if __name__ == "__main__":
    unittest.main()
