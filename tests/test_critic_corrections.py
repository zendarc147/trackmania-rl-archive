"""J4-15 regression tests. Games and training data here are SYNTHETIC, never TMNF."""
import copy
import hashlib
import json
import pathlib
import tempfile
import unittest
from unittest import mock

import numpy as np
import torch
from stable_baselines3.common.vec_env import DummyVecEnv

from trackmania_rl import observation as obs
from trackmania_rl.actions import make_codec
from trackmania_rl.env import TrackmaniaEnv
from trackmania_rl.gym_env import TrackmaniaGymEnv
from trackmania_rl.protocol import Action
from trackmania_rl.training import Trainer, EnvHandle, validate_config
from trackmania_rl.evaluation import load_policy, evaluate
from test_env import make_env, PROFILE
from test_training import CFG, synthetic_factory


def env_v2(**rules):
    old, game = make_env(**rules)
    return TrackmaniaEnv(game, PROFILE, old.encoder, old.tracker, old.reward_cfg, old.rules,
                         observation_schema=obs.EPISODE_SCHEMA_VERSION), game


def factory_v2(first_episode):
    env, _ = env_v2()
    env.episode = first_episode - 1
    return EnvHandle(env, lambda: None)


class EpisodeObservation(unittest.TestCase):
    def test_v1_unchanged_and_v2_timer_reaches_terminal(self):
        v1, _ = make_env(no_progress_ms=200)
        v2, _ = env_v2(no_progress_ms=200)
        a, _ = v1.reset(); b, _ = v2.reset()
        self.assertEqual(a, b[:25])
        self.assertEqual(b[-2:], [1.0, 0.0])
        for i in range(1, 5):
            t = v2.step(Action(0, False, False, 5))
            self.assertAlmostEqual(t.next_obs[-2], 1 - i / 4)
            self.assertEqual(t.obs[-2], 1 - (i - 1) / 4)
        self.assertTrue(t.terminated)
        self.assertFalse(t.truncated)
        self.assertEqual(t.status, 'abandoned')
        self.assertEqual(v2.reset()[0][-2:], [1.0, 0.0])

    def test_record_update_precedes_encoding_and_time_limit_bootstraps(self):
        env, _ = env_v2(time_limit_ms=200)
        env.reset()
        for _ in range(4):
            t = env.step(Action(0, True, False, 5))
        self.assertEqual(t.status, 'time_limit')
        self.assertTrue(t.truncated)
        self.assertFalse(t.terminated)
        self.assertAlmostEqual(t.next_obs[-2], 1 - (t.race_ms - env.best_race_ms) / env.rules.no_progress_ms)
        self.assertAlmostEqual(t.next_obs[-1], (env.best_s_m - env.last_projection.s_m) / env.tracker.line.length)
        self.assertGreater(t.discount, 0)
        gym = TrackmaniaGymEnv(env, make_codec('hybrid4_v1'))
        self.assertEqual(gym.observation_space.shape, (27,))
        self.assertTrue(gym.observation_space.contains(gym.reset()[0]))

    def test_same_physical_state_has_distinct_context_and_signed_gap(self):
        common = dict(race_ms=1000, no_progress_ms=5000, progress_s_m=10, best_s_m=12, length_m=100)
        self.assertNotEqual(obs.episode_features(best_race_ms=0, **common),
                            obs.episode_features(best_race_ms=900, **common))
        common['best_s_m'] = 9.995
        self.assertLess(obs.episode_features(best_race_ms=900, **common)[1], 0)
        with self.assertRaises(obs.ObservationError):
            obs.episode_features(best_race_ms=1100, **common)
        with self.assertRaises(ValueError):
            obs.observation_contract('unknown')


class CheckpointCorrections(unittest.TestCase):
    def setUp(self):
        torch.set_num_threads(1)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.cfg = copy.deepcopy(CFG)
        self.cfg.update(action_codec='hybrid4_v1', learner={'mode': 'sync', 'updates_per_transition': .5})
        self.cfg['sac'].update(hybrid_critic='q4', net_arch=[16, 16])
        self.cfg['budget']['transitions'] = 120
        self.src = self.root / 'source'
        Trainer(self.cfg, self.src, synthetic_factory(), install_signal_handler=False).run()
        self.ck = self.src / json.loads((self.src / 'checkpoints/latest.json').read_text())['dir']

    def build(self, cfg, name='target'):
        factory = factory_v2 if cfg.get('observation_schema') == obs.EPISODE_SCHEMA_VERSION else synthetic_factory()
        tr = Trainer(validate_config(cfg), self.root / name, factory, install_signal_handler=False)
        tr._open_files(); self.addCleanup(tr._close_files)
        tr.handle = factory(1)
        vec = DummyVecEnv([lambda: TrackmaniaGymEnv(tr.handle.env, tr.codec)])
        self.addCleanup(vec.close)
        m = tr.build_model(vec); self.addCleanup(m.logger.close)
        return m, tr

    def target_config(self, migration=False):
        cfg = copy.deepcopy(self.cfg)
        cfg['init_from'] = {'run': str(self.src), 'checkpoint': 'latest'}
        if migration:
            cfg['observation_schema'] = obs.EPISODE_SCHEMA_VERSION
            cfg['init_from']['migration'] = 'observation_v2'
        return cfg

    def test_same_schema_uses_actor_and_trains_without_new_warmup(self):
        m, _ = self.build(self.target_config())
        self.assertEqual(m.num_timesteps, 0)
        self.assertEqual(m.learning_starts, 0)
        self.assertEqual(m.replay_buffer.size(), 120)
        m._last_obs = m.env.reset()
        with mock.patch.object(m, 'predict', wraps=m.predict) as predict:
            m._sample_action(2000)
            predict.assert_called_once()
        updates = m._n_updates
        m.num_timesteps = 2
        from trackmania_rl.learner import make_learner
        m.num_timesteps = 0
        learner = make_learner(m, {'mode': 'sync', 'updates_per_transition': .5})
        m.num_timesteps = 2; learner.throttle()
        self.assertEqual(m._n_updates, updates + 1)

    def test_init_from_applies_config_entropy_targets(self):
        cfg = self.target_config()
        cfg['sac']['hybrid_target_entropy'] = [-0.5, 0.1386]
        m, _ = self.build(cfg)
        self.assertEqual(m.hybrid_target_entropy, [-0.5, 0.1386])
        self.assertEqual(m.replay_buffer.size(), 120)
        cfg['sac']['hybrid_target_entropy'] = [-0.5, 1.5]
        with self.assertRaises(ValueError):
            validate_config(cfg)

    def test_migration_preserves_actor_critics_targets_and_temperature(self):
        source, _ = load_policy(self.ck)
        before = hashlib.sha256((self.ck / 'model.zip').read_bytes()).hexdigest()
        m, _ = self.build(self.target_config(migration=True))
        self.assertEqual(m.replay_buffer.size(), 0)
        self.assertGreaterEqual(m.learning_starts, m.batch_size)
        self.assertFalse(m.actor.optimizer.state)
        self.assertFalse(m.critic.optimizer.state)
        self.assertFalse(m.ent_coef_optimizer.state)
        x = torch.randn(12, 25); extra = torch.randn(12, 2)
        expanded = torch.cat((x, extra), dim=1)
        with torch.no_grad():
            for a, b in zip(source.actor.distributions(x), m.actor.distributions(expanded)):
                torch.testing.assert_close(a, b)
            actions = source.actor(x)
            for name in ('critic', 'critic_target'):
                for a, b in zip(getattr(source, name)(x, actions), getattr(m, name)(expanded, actions)):
                    torch.testing.assert_close(a, b)
        torch.testing.assert_close(source.log_ent_coef, m.log_ent_coef)
        self.assertEqual(before, hashlib.sha256((self.ck / 'model.zip').read_bytes()).hexdigest())
        m._last_obs = m.env.reset()
        with mock.patch.object(m, 'predict', wraps=m.predict) as predict:
            m._sample_action(m.learning_starts)
            predict.assert_called_once()

    def test_schema_mismatch_requires_explicit_migration(self):
        cfg = self.target_config()
        cfg['observation_schema'] = obs.EPISODE_SCHEMA_VERSION
        with self.assertRaisesRegex(ValueError, 'explicit observation_v2'):
            self.build(cfg)

    def test_migration_checkpoint_resume_and_evaluation_contract(self):
        cfg = self.target_config(migration=True)
        cfg['budget']['transitions'] = 80
        cfg['critic_diagnostics'] = {'every_updates': 5, 'samples': 16}
        target = self.root / 'full_migration'
        st = Trainer(cfg, target, factory_v2, install_signal_handler=False).run()
        self.assertEqual(st['phase'], 'finished_budget')
        cfg['budget']['transitions'] = 100
        st = Trainer(cfg, target, factory_v2, resume=True, install_signal_handler=False).run()
        ck = target / st['latest_checkpoint']['dir']
        m, ts = load_policy(ck)
        self.assertTrue(m._use_loaded_policy)
        self.assertEqual(m.observation_space.shape, (27,))
        self.assertEqual(m._critic_probe['uniform']['observations'].shape[1], 27)
        self.assertEqual(ts['replay_buffer_size'], 100)
        self.assertEqual(ts['derived']['observation']['schema'], obs.EPISODE_SCHEMA_VERSION)
        self.assertEqual(m.predict(factory_v2(1).env.reset()[0])[0].shape, (5,))
        with self.assertRaisesRegex(ValueError, 'observation schema'):
            evaluate(make_env()[0], m, ts, episodes=1, out_dir=self.root/'eval', mode='sync', speed=1)
        with mock.patch('builtins.print'):
            result = evaluate(factory_v2(1).env, m, ts, episodes=1, max_steps=2,
                              out_dir=self.root/'eval_ok', mode='sync', speed=1)
        self.assertEqual(result['episodes'], 1)

    def test_untrained_checkpoint_keeps_remaining_random_warmup(self):
        cfg = copy.deepcopy(self.cfg); cfg['budget']['transitions'] = 20
        src = self.root / 'untrained'
        Trainer(cfg, src, synthetic_factory(), install_signal_handler=False).run()
        cfg['init_from'] = {'run': str(src)}
        m, _ = self.build(cfg)
        self.assertFalse(m._use_loaded_policy)
        self.assertEqual(m.learning_starts, 30)
        with mock.patch.object(m, 'predict') as predict:
            m._sample_action(m.learning_starts)
            predict.assert_not_called()

    def test_async_migration_resumes_during_fresh_replay_fill(self):
        cfg = self.target_config(migration=True)
        cfg['learner']['mode'] = 'async'
        cfg['critic_diagnostics'] = {'every_updates': 5, 'samples': 16}
        cfg['budget']['transitions'] = 20
        target = self.root / 'async_migration'
        first = Trainer(cfg, target, factory_v2, install_signal_handler=False).run()
        m, _ = load_policy(target / first['latest_checkpoint']['dir'])
        self.assertTrue(m._use_loaded_policy)
        self.assertEqual(m.learning_starts, 50)
        source, _ = load_policy(self.ck)
        self.assertEqual(m._n_updates, source._n_updates)
        with mock.patch.object(m, 'predict', return_value=(np.zeros((1, 5)), None)) as predict:
            m._sample_action(m.learning_starts)
            predict.assert_called_once()
        cfg['budget']['transitions'] = 100
        last = Trainer(cfg, target, factory_v2, resume=True, install_signal_handler=False).run()
        m, _ = load_policy(target / last['latest_checkpoint']['dir'])
        self.assertEqual(last['phase'], 'finished_budget')
        self.assertGreater(m._n_updates, source._n_updates)
        self.assertIn('uniform', m._critic_probe)

    def test_probe_terminal_targets_and_timeout_bootstrap(self):
        from trackmania_rl.critic_diagnostics import capture_probe, evaluate_probe
        m, _ = self.build(self.target_config())
        rb = m.replay_buffer
        rb.pos = 3; rb.full = False
        rb.observations[:3] = 0; rb.next_observations[:3] = 0
        rb.dones[:3, 0] = 1; rb.timeouts[:3, 0] = [0, 0, 1]
        m._critic_reward_config = dict(progress_mode='delta', progress_scale=100.,
                                     time_cost_per_s=1., finish_bonus=20.)
        rb.rewards[:3, 0] = [-.05, 19.95, -.05]
        probe = capture_probe(m, size=0, terminal_size=0)
        self.assertEqual(len(probe['abandon']['rewards']), 1)
        self.assertEqual(len(probe['finish']['rewards']), 1)
        self.assertEqual(len(probe['uniform']['rewards']), 3)
        result = evaluate_probe(m, probe)
        for key in ('abandon', 'finish'):
            group = probe[key]
            with torch.no_grad():
                q = torch.cat(m.critic(torch.as_tensor(group['observations']),
                                       torch.as_tensor(group['actions'])), dim=1)
                expected = (q - torch.as_tensor(group['rewards'])[:, None]).square().mean()
            self.assertAlmostEqual(result[key]['mse'], float(expected), places=5)
        # A timeout stays bootstrapped, unlike an actual terminal failure.
        timeout = {k: v[2:3] if k != 'id' else v for k, v in probe['uniform'].items()}
        a = evaluate_probe(m, {'timeout': timeout})['timeout']['mse']
        timeout['timeouts'] = np.zeros_like(timeout['timeouts'])
        b = evaluate_probe(m, {'timeout': timeout})['timeout']['mse']
        self.assertNotAlmostEqual(a, b, places=5)

    def test_diagnostics_are_fixed_read_only_and_preserve_rngs(self):
        from trackmania_rl.critic_diagnostics import capture_probe, evaluate_probe
        m, _ = self.build(self.target_config())
        probe = capture_probe(m, size=20)
        rng = torch.get_rng_state().clone(); nrng = np.random.get_state()
        weights = {k: v.clone() for k, v in m.policy.state_dict().items()}
        a = evaluate_probe(m, probe); b = evaluate_probe(m, probe)
        self.assertEqual(a, b)
        torch.testing.assert_close(torch.get_rng_state(), rng)
        np.testing.assert_array_equal(np.random.get_state()[1], nrng[1])
        for k, v in m.policy.state_dict().items():
            torch.testing.assert_close(v, weights[k])
        self.assertEqual(capture_probe(m, existing=probe)['uniform']['id'], probe['uniform']['id'])
        self.assertEqual(a['uniform']['count'], 20)


if __name__ == '__main__':
    unittest.main()
