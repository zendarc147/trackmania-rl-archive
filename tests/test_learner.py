"""Off-game tests for the J4 learner options: q4 hybrid critic, update ratio, async learner.

EVERY GAME IN THIS FILE IS SYNTHETIC (tests/test_env.SyntheticGame, an invented 1-D car that
speaks the bridge message format) and every tensor batch is random synthetic data. These tests
check plumbing and mathematical equivalences, not learning performance nor the real game.
"""
import json
import pathlib
import pickle
import tempfile
import unittest

import numpy as np
import torch

from trackmania_rl import learner as ln
from trackmania_rl.training import Trainer, model_class_for, validate_config

from test_training import CFG, synthetic_factory


def cfg_with(**over):
    cfg = json.loads(json.dumps(CFG))
    for k, v in over.items():
        if k == "sac":
            cfg["sac"].update(v)
        else:
            cfg[k] = v
    return cfg


class LearnerConfig(unittest.TestCase):
    def test_absent_section_keeps_historical_behaviour(self):
        self.assertIsNone(ln.learner_config(CFG))

    def test_schedule_target_is_floor_of_ratio_after_learning_starts(self):
        class M:
            num_timesteps, learning_starts = 0, 50
        sch = ln._Schedule(M(), 0.3)
        self.assertEqual([sch.target(n) for n in (0, 50, 53, 60, 150)], [0, 0, 0, 3, 30])
        M.num_timesteps = 100                     # resumed session: counted from its start
        self.assertEqual(ln._Schedule(M(), 2).target(110), 20)

    def test_invalid_sections_are_refused(self):
        for learner in ({"mode": "x"}, {"updates_per_transition": 0}, {"max_wait_ms": 1500},
                        {"typo": 1}, {"chunk": 0}):
            with self.assertRaises(ValueError, msg=learner):
                validate_config(cfg_with(learner=learner))
        with self.assertRaises(ValueError):   # ratio and SB3 schedule would disagree
            validate_config(cfg_with(learner={"updates_per_transition": 1},
                                     sac={"gradient_steps": 2}))
        with self.assertRaises(ValueError):   # q4 critic only for the hybrid codec
            validate_config(cfg_with(sac={"hybrid_critic": "q4"}))
        validate_config(cfg_with(action_codec="hybrid4_v1", sac={"hybrid_critic": "q4"},
                                 learner={"mode": "async", "updates_per_transition": 0.5}))


class Q4Critic(unittest.TestCase):
    """SYNTHETIC tensors: the q4 critic keeps the SB3 critic contract and the hybrid math."""

    def setUp(self):
        import gymnasium as gym
        from trackmania_rl.hybrid_sac import HybridQ4Policy, HybridQ4SAC

        class Shape(gym.Env):
            observation_space = gym.spaces.Box(-5, 5, (25,), np.float32)
            action_space = gym.spaces.Box(-1, 1, (5,), np.float32)

            def reset(self, **k):
                return np.zeros(25, np.float32), {}

            def step(self, a):
                return np.zeros(25, np.float32), 0.0, False, False, {}

        torch.manual_seed(0)
        self.m = HybridQ4SAC(HybridQ4Policy, Shape(), policy_kwargs={"net_arch": [32, 32]},
                             buffer_size=500, batch_size=16, learning_starts=0, device="cpu", seed=0)

    def test_forward_selects_the_replayed_command(self):
        critic = self.m.critic
        obs = torch.randn(6, 25)
        steer = torch.rand(6, 1) * 2 - 1
        idx = torch.tensor([0, 1, 2, 3, 2, 0])
        actions = torch.cat([steer, torch.nn.functional.one_hot(idx, 4).float() * 2 - 1], 1)
        with torch.no_grad():
            per_cmd = critic.all_q(obs, steer)
            selected = critic(obs, actions)
        self.assertEqual(len(selected), 2)
        for q4, q in zip(per_cmd, selected):
            self.assertEqual(q.shape, (6, 1))
            torch.testing.assert_close(q[:, 0], q4[torch.arange(6), idx])

    def test_expected_q_is_elementwise_min_over_twins(self):
        from trackmania_rl.hybrid_sac import HybridQ4SAC
        obs, steer = torch.randn(5, 25), torch.rand(5, 1)
        with torch.no_grad():
            q1, q2 = self.m.critic.all_q(obs, steer)
            e = HybridQ4SAC._expected_q(self.m.critic, obs, steer)
        self.assertEqual(e.shape, (5, 4))
        torch.testing.assert_close(e, torch.minimum(q1, q2))

    def test_critic_has_no_action_input_and_trains(self):
        first = self.m.critic.q_networks[0][0]
        self.assertEqual(first.in_features, 25 + 1)       # observation + steer only
        self.assertEqual(self.m.critic.q_networks[0][-1].out_features, 4)
        ids = {id(p) for p in self.m.critic.parameters()}
        self.assertTrue(all(id(p) in ids for q in self.m.critic.q_networks for p in q.parameters()))
        rng = np.random.default_rng(0)
        for _ in range(64):
            a = np.eye(4, dtype=np.float32)[rng.integers(4)] * 2 - 1
            self.m.replay_buffer.add(rng.normal(size=(1, 25)).astype(np.float32),
                                     rng.normal(size=(1, 25)).astype(np.float32),
                                     np.concatenate([[rng.uniform(-1, 1)], a])[None].astype(np.float32),
                                     np.array([rng.normal()]), np.array([False]), [{}])
        from stable_baselines3.common.logger import configure
        self.m.set_logger(configure(None, []))
        before = [p.detach().clone() for p in self.m.critic.parameters()]
        self.m.train(gradient_steps=3, batch_size=16)
        self.assertTrue(any(not torch.equal(b, p) for b, p in zip(before, self.m.critic.parameters())))


class LockedBuffer(unittest.TestCase):
    def test_pickle_roundtrip_and_conversion(self):
        import gymnasium as gym
        from stable_baselines3.common.buffers import ReplayBuffer
        rb = ReplayBuffer(10, gym.spaces.Box(-1, 1, (2,)), gym.spaces.Box(-1, 1, (1,)), device="cpu")
        ln.make_locked(rb)
        rb.add(np.zeros((1, 2)), np.zeros((1, 2)), np.zeros((1, 1)), np.zeros(1), np.zeros(1), [{}])
        rb2 = pickle.loads(pickle.dumps(rb))
        self.assertIsInstance(rb2, ln.LockedReplayBuffer)
        self.assertEqual(rb2.size(), 1)
        rb2.sample(1)            # lock recreated lazily after unpickling


class TrainerModes(unittest.TestCase):
    """SYNTHETIC game: every learner mode runs, checkpoints, resumes and evaluates."""

    def _run(self, cfg, budget, resume_budget=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run = pathlib.Path(tmp.name) / "run"
        cfg["budget"]["transitions"] = budget
        st = Trainer(cfg, run, synthetic_factory(), install_signal_handler=False).run()
        self.assertEqual(st["phase"], "finished_budget")
        self.assertEqual(st["timesteps"], budget)
        if resume_budget:
            cfg2 = json.loads((run / "config.json").read_text())["config"]
            cfg2["budget"]["transitions"] = resume_budget
            st = Trainer(cfg2, run, synthetic_factory(), resume=True, install_signal_handler=False).run()
            self.assertEqual(st["timesteps"], resume_budget)
        ck = run / json.loads((run / "checkpoints" / "latest.json").read_text())["dir"]
        return run, st, json.loads((ck / "trainer_state.json").read_text()), ck

    def test_sync_ratio_quarter_updates(self):
        cfg = cfg_with(learner={"mode": "sync", "updates_per_transition": 0.25})
        run, st, ts, _ = self._run(cfg, 250)     # exact budget, no SB3 train_freq overshoot
        # floor(0.25 x (250 - learning_starts 50)) gradient steps, all in this session
        self.assertEqual(ts["gradient_updates"], 50)
        self.assertEqual(st["learner"]["lag_updates"], 0)
        self.assertEqual(ts["learner"]["mode"], "sync")

    def test_sync_ratio_one_matches_legacy_update_count(self):
        legacy = self._run(cfg_with(), 200)[2]["gradient_updates"]
        new = self._run(cfg_with(learner={"mode": "sync", "updates_per_transition": 1}), 200)[2]
        self.assertEqual(new["gradient_updates"], 150)
        self.assertLessEqual(abs(legacy - new["gradient_updates"]), 1)   # SB3 starts at n > 50

    def test_async_q4_hybrid_train_resume_eval(self):
        from trackmania_rl.evaluation import load_policy
        from trackmania_rl.hybrid_sac import HybridQ4SAC
        cfg = cfg_with(action_codec="hybrid4_v1", sac={"hybrid_critic": "q4"},
                       learner={"mode": "async", "updates_per_transition": 0.5, "max_wait_ms": 200})
        run, st, ts, ck = self._run(cfg, 300, resume_budget=380)
        self.assertEqual(st["invalid_transitions"], 0)
        self.assertEqual(ts["learner"]["mode"], "async")
        self.assertGreater(ts["gradient_updates"], 0)
        # a bounded wait keeps the learner close to its target ratio on the synthetic game
        self.assertLessEqual(st["learner"]["lag_updates"], cfg["learner"].get("max_update_lag", 32) + 8)
        kinds = [json.loads(x)["kind"] for x in (run / "incidents.jsonl").read_text().splitlines()]
        self.assertIn("learner_start", kinds)
        self.assertIn("learner_stop", kinds)
        model, state = load_policy(ck)
        self.assertIsInstance(model, HybridQ4SAC)
        a = model.predict(np.zeros(25, np.float32), deterministic=True)[0]
        self.assertEqual(sorted(a[1:].tolist()), [-1.0, -1.0, -1.0, 1.0])

    def test_async_q4_unlimited_resume_keeps_learning_until_stop(self):
        cfg = cfg_with(action_codec="hybrid4_v1", sac={"hybrid_critic": "q4"},
                       learner={"mode": "async", "updates_per_transition": 0.5,
                                "max_wait_ms": 200})
        run, before, _, _ = self._run(cfg, 100)
        cfg["budget"]["transitions"] = None
        cfg["checkpoint_every_transitions"] = 20
        trainer = Trainer(cfg, run, synthetic_factory(), resume=True,
                          install_signal_handler=False)
        original = trainer.after_store

        def stop_after_chunks(dones, infos, stored):
            if trainer.model.num_timesteps >= 155:
                (run / "STOP").write_text("test")
            original(dones, infos, stored)

        trainer.after_store = stop_after_chunks
        after = trainer.run()
        self.assertEqual(after["phase"], "stopped")
        self.assertEqual(after["stop_reason"], "stop_file")
        self.assertGreater(after["timesteps"], before["timesteps"])
        self.assertGreater(after["learner"]["updates_session"], 0)
        self.assertFalse(trainer.learner.thread.is_alive())

    def test_async_threshold_stop_file(self):
        cfg = cfg_with(learner={"mode": "async", "updates_per_transition": 1})
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        run = pathlib.Path(tmp.name) / "run"
        cfg["budget"]["transitions"] = 400
        tr = Trainer(cfg, run, synthetic_factory(), install_signal_handler=False)
        real = tr.after_store

        def after_store(dones, infos, stored):
            if tr.model.num_timesteps >= 150:
                (run / "STOP").write_text("test")
            real(dones, infos, stored)
        tr.after_store = after_store
        st = tr.run()
        self.assertEqual(st["phase"], "stopped")
        self.assertEqual(st["timesteps"], 150)
        self.assertFalse(tr.learner.thread.is_alive())

    def test_old_hybrid_configs_still_use_action_input_critic(self):
        from trackmania_rl.hybrid_sac import HybridSAC, HybridQ4SAC
        cls, _ = model_class_for(cfg_with(action_codec="hybrid4_v1"))
        self.assertIs(cls, HybridSAC)
        self.assertIsNot(cls, HybridQ4SAC)


class HybridEntropyPerHead(unittest.TestCase):
    """J4-07 on a SYNTHETIC one-step bandit (not the game): the context says which command pays
    and where to steer. With the J4-02 single target (1.69 nats) the command head stayed ~uniform."""

    def test_learns_the_command_and_keeps_two_temperatures(self):
        import gymnasium as gym
        from stable_baselines3.common.logger import configure
        from trackmania_rl.hybrid_sac import DEFAULT_TARGET_ENTROPY, HybridPolicy, HybridSAC

        class Bandit(gym.Env):
            observation_space = gym.spaces.Box(-1, 1, (2,), np.float32)
            action_space = gym.spaces.Box(-1, 1, (5,), np.float32)

            def _obs(self):
                self.c = float(self.np_random.choice((-1.0, 1.0)))
                return np.array([self.c, 0.0], np.float32)

            def reset(self, seed=None, **k):
                super().reset(seed=seed)
                return self._obs(), {}

            def step(self, a):
                good = 1 if self.c > 0 else 2                       # gas or brake
                r = float(np.argmax(a[1:]) == good) - abs(float(a[0]) - 0.5 * self.c)
                return self._obs(), r, True, False, {}

        torch.manual_seed(0)
        m = HybridSAC(HybridPolicy, Bandit(), policy_kwargs={"net_arch": [64, 64]}, gamma=0.9,
                      ent_coef="auto_0.1",
                      learning_starts=200, batch_size=64, buffer_size=5000, device="cpu", seed=0)
        m.set_logger(configure(None, []))
        self.assertEqual(m.log_ent_coef.numel(), 2)
        m.learn(1500)
        with torch.no_grad():
            obs = torch.tensor([[1.0, 0.0], [-1.0, 0.0]])
            mean, _, logits = m.actor.distributions(obs)
            probs = torch.softmax(logits, -1)
        self.assertGreater(float(probs[0, 1]), 0.6, probs)          # uniform would be 0.25
        self.assertGreater(float(probs[1, 2]), 0.6, probs)
        self.assertGreater(float(torch.tanh(mean[0])), 0.2)          # steers towards +0.5
        self.assertLess(float(torch.tanh(mean[1])), -0.2)
        alpha = m.log_ent_coef.detach().exp()
        self.assertTrue(bool((alpha < 1.0).all()), alpha)            # no runaway temperature
        self.assertEqual(m.hybrid_target_entropy, list(DEFAULT_TARGET_ENTROPY))
        # a checkpoint with the single J4-02 temperature is refused for training
        m.log_ent_coef = torch.zeros(1, requires_grad=True)
        with self.assertRaises(ValueError):
            m.train(gradient_steps=1, batch_size=16)

    def test_config_knob_is_hybrid_only_and_bounded(self):
        from trackmania_rl.hybrid_sac import HybridSAC
        with self.assertRaises(ValueError):
            validate_config(cfg_with(sac={"hybrid_target_entropy": [-1.0, 0.4]}))
        validate_config(cfg_with(action_codec="hybrid4_v1", sac={"hybrid_target_entropy": [-1.0, 0.4]}))
        with self.assertRaises(ValueError):
            HybridSAC("MlpPolicy", "Pendulum-v1", hybrid_target_entropy=[-1.0, 1.5])
        with self.assertRaises(ValueError):       # unreachable steer target (uniform = ln 2)
            HybridSAC("MlpPolicy", "Pendulum-v1", hybrid_target_entropy=[0.7, 0.4])


class SaturatedSteer(unittest.TestCase):
    """SYNTHETIC tensors: a steering mean far past tanh saturation (J4-07 collapse)."""

    def test_log_prob_stays_that_of_a_near_deterministic_head(self):
        import gymnasium as gym
        from trackmania_rl.hybrid_sac import HybridPolicy, HybridSAC

        class Shape(gym.Env):
            observation_space = gym.spaces.Box(-5, 5, (3,), np.float32)
            action_space = gym.spaces.Box(-1, 1, (5,), np.float32)

        m = HybridSAC(HybridPolicy, Shape(), policy_kwargs={"net_arch": [8]}, device="cpu", seed=0)
        with torch.no_grad():
            m.actor.mu.weight.zero_()
            m.actor.mu.bias.fill_(1e6)                 # tanh(mean) == 1.0 in float32
            m.actor.log_std.weight.zero_()
            m.actor.log_std.bias.fill_(-5.0)
        steer, log_steer, *_ = m.actor.sample_heads(torch.zeros(4, 3))
        self.assertTrue(bool((steer > 0.999).all()))
        # a saturated head is nearly deterministic: large POSITIVE log-density, never ~ -1e16
        self.assertTrue(bool(torch.isfinite(log_steer).all()))
        self.assertTrue(bool((log_steer > 0).all()), log_steer)

    def test_non_finite_loss_stops_training(self):
        import gymnasium as gym
        from stable_baselines3.common.logger import configure
        from trackmania_rl.hybrid_sac import HybridPolicy, HybridSAC

        class Shape(gym.Env):
            observation_space = gym.spaces.Box(-5, 5, (3,), np.float32)
            action_space = gym.spaces.Box(-1, 1, (5,), np.float32)

        m = HybridSAC(HybridPolicy, Shape(), policy_kwargs={"net_arch": [8]}, device="cpu", seed=0,
                      buffer_size=100, batch_size=4)
        m.set_logger(configure(None, []))
        for _ in range(8):
            a = np.array([[0.0, 1, -1, -1, -1]], np.float32)
            m.replay_buffer.add(np.zeros((1, 3), np.float32), np.zeros((1, 3), np.float32), a,
                                np.array([float("inf")]), np.array([False]), [{}])
        with self.assertRaises(FloatingPointError):
            m.train(gradient_steps=1, batch_size=4)


if __name__ == "__main__":
    unittest.main()
