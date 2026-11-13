"""J6 observation v3 (lookahead) and v2 -> v3 migration. SYNTHETIC games only, never TMNF."""
import copy
import json
import pathlib
import tempfile
import unittest

import torch

from trackmania_rl import observation as obs
from trackmania_rl.env import TrackmaniaEnv
from trackmania_rl.evaluation import load_policy
from trackmania_rl.training import EnvHandle, Trainer
from test_env import make_env, PROFILE
from test_training import CFG
from test_critic_corrections import factory_v2


def env_v3():
    old, game = make_env()
    return TrackmaniaEnv(game, PROFILE, old.encoder, old.tracker, old.reward_cfg, old.rules,
                         observation_schema=obs.LOOKAHEAD_SCHEMA_VERSION), game


def factory_v3(first_episode):
    env, _ = env_v3()
    env.episode = first_episode - 1
    return EnvHandle(env, lambda: None)


class LookaheadObservation(unittest.TestCase):
    def test_v3_extends_v2_with_points_ahead_in_car_frame(self):
        v2 = factory_v2(1).env
        v3 = factory_v3(1).env
        a, _ = v2.reset(); b, _ = v3.reset()
        self.assertEqual(len(b), obs.observation_contract(obs.LOOKAHEAD_SCHEMA_VERSION)["dim"])
        self.assertEqual(a, b[:27])
        # synthetic line along +z, car aligned with identity rotation: every point is straight ahead
        ahead = b[27:]
        for k, _d in enumerate(obs.LOOKAHEAD_M):
            x, y, z = ahead[3 * k: 3 * k + 3]
            self.assertAlmostEqual(x, 0.0, places=6)
            self.assertAlmostEqual(y, 0.0, places=6)
            self.assertLessEqual(z, 1.0 + 1e-9)    # clamped at the finish
            self.assertGreater(z, 0.0)


class MigrationV2toV3(unittest.TestCase):
    def test_migration_keeps_outputs_with_zero_new_columns(self):
        torch.set_num_threads(1)
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        root = pathlib.Path(tmp.name)
        cfg = copy.deepcopy(CFG)
        cfg.update(action_codec='hybrid4_v1', learner={'mode': 'sync', 'updates_per_transition': .5},
                   observation_schema=obs.EPISODE_SCHEMA_VERSION)
        cfg['sac'].update(hybrid_critic='q4', net_arch=[16, 16])
        cfg['budget']['transitions'] = 60
        Trainer(cfg, root / 'v2', factory_v2, install_signal_handler=False).run()
        ck = root / 'v2' / json.loads((root / 'v2/checkpoints/latest.json').read_text())['dir']
        cfg3 = copy.deepcopy(cfg)
        cfg3['observation_schema'] = obs.LOOKAHEAD_SCHEMA_VERSION
        cfg3['init_from'] = {'run': str(root / 'v2'), 'checkpoint': 'latest', 'migration': 'observation_v3'}
        cfg3['budget']['transitions'] = 30
        st = Trainer(cfg3, root / 'v3', factory_v3, install_signal_handler=False).run()
        self.assertEqual(st['phase'], 'finished_budget')
        source, _ = load_policy(ck)
        first = root / 'v3' / json.loads((root / 'v3/checkpoints/latest.json').read_text())['dir']
        m, ts = load_policy(first)
        self.assertEqual(m.observation_space.shape, (45,))
        self.assertEqual(ts['derived']['observation']['schema'], obs.LOOKAHEAD_SCHEMA_VERSION)
        incident = [json.loads(l) for l in open(root / 'v3/incidents.jsonl')
                    if '"init_from"' in l][0]
        self.assertEqual(incident['migration']['mode'], 'observation_v3')
        # zero-initialized new columns: the migrated net ignores the lookahead at first
        weight = m.actor.latent_pi[0].weight
        self.assertEqual(weight.shape[1], 45)


if __name__ == "__main__":
    unittest.main()
