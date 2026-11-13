"""Off-game tests for the J3 episode environment and reward v1.

EVERY FIXTURE IN THIS FILE IS SYNTHETIC. `SyntheticGame` is a hand-written 1-D car on a
straight synthetic line that speaks the bridge message format; it is NOT TrackMania and does
not validate the game integration. It tests the environment contract and the reward rules
(docs/REWARDS.md §5). Real-game evidence is in docs/reports/J3-environnement.md.
"""
import math
import unittest

from trackmania_rl import observation as obs
from trackmania_rl import reward as rw
from trackmania_rl.bridge import BridgeError
from trackmania_rl.env import ERROR, EnvUsageError, EpisodeRules, TrackmaniaEnv
from trackmania_rl.geometry import ProgressTracker, ReferenceLine
from trackmania_rl.protocol import Action

from test_geometry import SYNTHETIC_UID, figure_with_overpass, straight, synthetic_prepared

LENGTH = 300.0
PROFILE = {"name": "synthetic", "uid": SYNTHETIC_UID, "checkpoint_count": 3,
           "episode": {"time_limit_ms": 60000, "no_progress_ms": 5000}}
GAS, BRAKE, COAST = Action(0.0, True, False), Action(0.0, False, True), Action(0.0, False, False)


class SyntheticGame:
    """SYNTHETIC stand-in for the bridge (same message shapes, invented physics)."""

    def __init__(self, cp_at=(100.0, 200.0), finish_at=LENGTH, accel=8.0, uid=SYNTHETIC_UID):
        self.cp_at, self.finish_at, self.accel, self.uid = cp_at, finish_at, accel, uid
        self.sent, self.queue = [], []
        self.fault = None          # one-shot fault injected on the next action
        self.contact = [True] * 4
        self.sliding = [False] * 4
        self.tick = 100000
        self.seq = 0
        self.teleport = None

    # bridge API used by the environment
    def configure(self, sync, timeout_ms, stream_every, auto_restart=False):
        return {"event": "config", "sync": bool(sync), "timeout_ms": timeout_ms,
                "stream_every": stream_every, "auto_restart": bool(auto_restart)}

    def reset(self, episode, timeout=15.0):
        self.episode, self.race, self.z, self.v, self.cps, self.finished = episode, 0, 0.0, 0.0, 0, False
        self.source_seq = -1
        self.tick += 3000
        return self._state("start", 0)

    def send_line(self, line):
        if self.fault == "disconnect":
            raise BridgeError("send failed: broken pipe")
        self.sent.append(line)
        p = line.split()
        if p[0] != "A":
            return 0.0
        ep, aid, steer, gas, brake, ticks = int(p[1]), int(p[2]), int(p[4]), p[5] == "1", p[6] == "1", int(p[7])
        prior_source_seq = self.source_seq
        self.source_seq = int(p[3])
        fault, self.fault = self.fault, None
        if fault == "silence":
            return 0.0
        if fault == "released":
            self.queue.append({"kind": "event", "event": "released", "reason": "action_timeout",
                               "episode": ep})
            return 0.0
        if fault == "finish_same_tick":
            # SYNTHETIC: checkpoint callback follows a boundary at the same game tick.
            self.cps, self.finished = len(self.cp_at) + 1, True
            self.queue.append(self._state("finish", aid))
            return 0.0
        if fault == "finish_same_tick_moved":
            # SYNTHETIC: the game can report post-physics movement before its
            # race/tick counters advance in the checkpoint callback.
            self.z += 0.5
            self.cps, self.finished = len(self.cp_at) + 1, True
            self.queue.append(self._state("finish", aid))
            return 0.0
        if fault == "finish_same_tick_teleport":
            # SYNTHETIC: a large jump at an unchanged tick remains invalid.
            self.z += 100.0
            self.cps, self.finished = len(self.cp_at) + 1, True
            self.queue.append(self._state("finish", aid))
            return 0.0
        if fault == "finish_same_tick_bad_position":
            self.cps, self.finished = len(self.cp_at) + 1, True
            st = self._state("finish", aid)
            st["position"] = ["bad", 0.0, 0.0]
            self.queue.append(st)
            return 0.0
        if fault == "finish_before_action":
            # SYNTHETIC: real-time game finishes after the previous boundary but
            # before the next action reaches the bridge.
            self.cps, self.finished = len(self.cp_at) + 1, True
            self.source_seq = prior_source_seq
            self.queue.append(self._state("finish", aid - 1))
            self.queue.append({"kind": "event", "event": "released", "reason": "finish",
                               "episode": ep, "action_id": aid - 1})
            return 0.0
        reason = "boundary"
        for _ in range(ticks):
            a = (self.accel if gas else 0.0) - (12.0 if brake else 0.0)
            if brake and self.v <= 0:
                a = -4.0                                   # reverse
            self.v += a * 0.01
            self.z += self.v * 0.01
            self.tick += 10
            self.race += 10
            while self.cps < len(self.cp_at) and self.z >= self.cp_at[self.cps]:
                self.cps += 1
            if self.cps == len(self.cp_at) and self.z >= self.finish_at:
                self.cps, self.finished, reason = self.cps + 1, True, "finish"
                break
        st = self._state(reason, aid)
        if fault == "stale":
            st["tick_ms"] -= 10
        elif fault == "nan":
            st["velocity"] = [float("nan"), 0.0, 0.0]
        elif fault == "uid":
            st["map_uid"] = "OTHER"
        elif fault == "cp_drop":
            st["checkpoints"] = -1 if self.cps == 0 else self.cps - 1
        elif fault == "fake_finish":
            st["finished"], st["reason"] = True, "finish"
        elif fault == "wrong_action":
            st["action_id"] = aid - 1
        if self.teleport is not None:
            st["position"] = self.teleport
        self.queue.append({"kind": "event", "event": "heartbeat", "episode": ep})
        self.queue.append(st)
        return 0.0

    def wait_for(self, predicate, timeout):
        while self.queue:
            m = self.queue.pop(0)
            if predicate(m):
                return m
        raise BridgeError("timeout")

    def _state(self, reason, aid):
        self.seq += 1
        return {"kind": "state", "reason": reason, "episode": self.episode, "seq": self.seq,
                "action_id": aid, "source_seq": self.source_seq,
                "tick_ms": self.tick, "race_ms": self.race,
                "map_uid": self.uid, "position": [0.0, 0.0, self.z],
                "rotation_matrix": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
                "velocity": [0.0, 0.0, self.v], "angular_velocity": [0.0, 0.0, 0.0],
                "gear": 1 if self.v > 0 else 0, "turning_rate": 0.0,
                "wheel_contact": list(self.contact), "wheel_sliding": list(self.sliding),
                "checkpoints": self.cps, "finished": self.finished}


def synthetic_norm():
    tr = ProgressTracker(ReferenceLine(synthetic_prepared(straight(LENGTH))))
    tr.reset()
    proj = tr.update([0.0, 0.0, 5.0], 0, 0)
    g = SyntheticGame()
    g.reset(1)
    rows = []
    for v in (0.0, 10.0, 30.0):
        g.v = v
        rows.append(obs.raw_features(g._state("start", 0), proj))
    return obs.fit_normalization(rows, data_kind="synthetic", sources=["synthetic"],
                                 map_uid=SYNTHETIC_UID, reference_sha256="synthetic")


NORM = synthetic_norm()


def make_env(game=None, prepared=None, reward_cfg=None, profile=PROFILE, ticks=5, **rules):
    game = game or SyntheticGame()
    line = ReferenceLine(prepared or synthetic_prepared(straight(LENGTH)))
    env = TrackmaniaEnv(game, profile, obs.Encoder(NORM, profile["uid"]), ProgressTracker(line),
                        reward_cfg or rw.RewardConfig(), EpisodeRules.from_profile(profile, **rules),
                        action_ticks=ticks)
    return env, game


def run(env, policy, max_steps=5000):
    """Drive one episode with a scripted SYNTHETIC controller; return the transitions."""
    env.reset()
    out = []
    for i in range(max_steps):
        t = env.step(policy(i, env))
        out.append(t)
        if t.done:
            break
    return out


def ret(transitions):
    return rw.discounted_return([rw.RewardBreakdown(**t.reward_components) for t in transitions])


class RealtimeMode(unittest.TestCase):
    """SYNTHETIC: a late boundary is an error in sync mode, accepted (bounded) in real-time."""

    def _late_step(self, env, game, late_ms):
        env.reset()
        orig = game._state

        def late_state(reason, aid):
            st = orig(reason, aid)
            st["tick_ms"] += late_ms
            st["race_ms"] += late_ms
            game.tick += late_ms
            game.race += late_ms
            return st
        game._state = late_state
        return env.step(Action(0.0, True, False, 5))

    def test_sync_rejects_late_boundary(self):
        env, game = make_env()
        t = self._late_step(env, game, 10)
        self.assertFalse(t.valid)

    def test_realtime_accepts_bounded_lag_only(self):
        env, game = make_env()
        env.realtime, env.realtime_max_lag_ms = True, 20
        t = self._late_step(env, game, 10)
        self.assertTrue(t.valid)
        self.assertEqual(t.dt_ms, 60)
        env2, game2 = make_env()
        env2.realtime, env2.realtime_max_lag_ms = True, 20
        self.assertFalse(self._late_step(env2, game2, 30).valid)


class ResetAndTransitionContract(unittest.TestCase):
    def test_reset_returns_first_observation_and_no_transition(self):
        env, game = make_env()
        o, info = env.reset()
        self.assertEqual(len(o), obs.DIM)
        self.assertEqual(info["state"]["race_ms"], 0)
        self.assertEqual(info["episode"], 1)
        self.assertEqual(game.sent[0], "REL")      # inputs released before any reset

    def test_step_before_reset_and_wrong_duration_are_usage_errors(self):
        env, _ = make_env()
        with self.assertRaises(EnvUsageError):
            env.step(GAS)
        env.reset()
        with self.assertRaises(EnvUsageError):
            env.step(Action(0.0, True, False, ticks=10))

    def test_transition_links_state_action_duration_and_next_state(self):
        env, game = make_env()
        o0, _ = env.reset()
        t1 = env.step(GAS)
        t2 = env.step(GAS)
        self.assertTrue(t1.valid and t2.valid)
        self.assertEqual((t1.action_id, t2.action_id), (1, 2))
        self.assertEqual(t1.obs, o0)
        self.assertEqual(t2.obs, t1.next_obs)
        self.assertEqual(t1.dt_ms, 50)
        self.assertEqual(t2.race_ms, 100)
        self.assertEqual(t1.status, rw.RUNNING)
        self.assertEqual(t1.discount, rw.RewardConfig().gamma(0.05))
        a = [line for line in game.sent if line.startswith("A ")]
        self.assertEqual(a[0].split()[:3], ["A", "1", "1"])

    def test_new_episode_after_reset_rejects_old_ids_and_restarts_progress(self):
        env, game = make_env()
        run(env, lambda i, e: GAS, max_steps=40)
        s_before = env.last_projection.s_m
        o, info = env.reset()
        self.assertEqual(info["episode"], 2)
        self.assertGreater(s_before, 5.0)
        self.assertLess(info["projection"].s_m, 1.0)
        self.assertEqual(env.action_id, 0)


class Outcomes(unittest.TestCase):
    def test_finish_is_terminal_with_bonus_and_zero_discount(self):
        env, _ = make_env()
        tr = run(env, lambda i, e: GAS)
        last = tr[-1]
        self.assertEqual(last.status, rw.FINISHED)
        self.assertTrue(last.terminated and not last.truncated and last.valid)
        self.assertEqual(last.discount, 0.0)
        self.assertEqual(last.reward_components["finish"], rw.RewardConfig().finish_bonus)
        self.assertLessEqual(last.dt_ms, 50)
        self.assertTrue(all(t.status == rw.RUNNING for t in tr[:-1]))
        with self.assertRaises(EnvUsageError):
            env.step(GAS)

    def test_same_tick_confirmed_finish_is_valid_without_invented_time(self):
        game = SyntheticGame(finish_at=10000.0)
        env, _ = make_env(game, reward_cfg=rw.RewardConfig(
            progress_mode="delta", finish_bonus=20.0, discount_per_second=0.905))
        env.reset()
        while game.z < LENGTH - 2.0:
            self.assertEqual(env.step(GAS).status, rw.RUNNING)
        game.fault = "finish_same_tick"
        t = env.step(GAS)
        self.assertTrue(t.valid)
        self.assertEqual(t.status, rw.FINISHED)
        self.assertEqual(t.dt_ms, 0)
        self.assertEqual(t.reward_components["time"], 0.0)
        self.assertEqual(t.reward_components["progress"], 0.0)
        self.assertEqual(t.reward_components["finish"], 20.0)
        self.assertEqual(t.discount, 0.0)

    def test_realtime_finish_before_next_action_is_not_lost_to_release_event(self):
        game = SyntheticGame(finish_at=10000.0)
        env, _ = make_env(game, reward_cfg=rw.RewardConfig(
            progress_mode="delta", finish_bonus=20.0, discount_per_second=0.905))
        env.realtime, env.realtime_max_lag_ms = True, 20
        env.reset()
        while game.z < LENGTH - 2.0:
            self.assertEqual(env.step(GAS).status, rw.RUNNING)
        game.fault = "finish_before_action"
        t = env.step(GAS)
        self.assertTrue(t.valid)
        self.assertEqual(t.status, rw.FINISHED)
        self.assertEqual(t.dt_ms, 0)
        self.assertTrue(t.info["finish_before_action"])
        self.assertEqual(t.reward_components["finish"], 20.0)
        self.assertEqual(game.sent[-1], "REL")

    def test_same_tick_finish_with_bounded_movement_keeps_bonus_not_progress(self):
        env, game = make_env(reward_cfg=rw.RewardConfig(
            progress_mode="delta", finish_bonus=20.0, discount_per_second=0.905))
        env.reset()
        env.step(GAS)
        game.fault = "finish_same_tick_moved"
        t = env.step(GAS)
        self.assertTrue(t.valid)
        self.assertEqual(t.status, rw.FINISHED)
        self.assertEqual(t.dt_ms, 0)
        self.assertEqual(t.reward_components["progress"], 0.0)
        self.assertEqual(t.reward_components["finish"], 20.0)

    def test_same_tick_finish_with_implausible_movement_is_rejected(self):
        env, game = make_env()
        env.reset()
        env.step(GAS)
        game.fault = "finish_same_tick_teleport"
        t = env.step(GAS)
        self.assertFalse(t.valid)
        self.assertEqual(t.status, ERROR)
        self.assertIsNone(t.reward)

    def test_same_tick_finish_with_malformed_position_is_invalid_not_a_crash(self):
        env, game = make_env()
        env.reset()
        env.step(GAS)
        game.fault = "finish_same_tick_bad_position"
        t = env.step(GAS)
        self.assertFalse(t.valid)
        self.assertEqual(t.status, ERROR)

    def test_zero_duration_reward_cannot_pay_progress_or_running_time(self):
        cfg = rw.RewardConfig(progress_mode="delta", finish_bonus=20.0)
        with self.assertRaises(ValueError):
            rw.compute(cfg, 0.9, 1.0, 0.0, rw.FINISHED)
        with self.assertRaises(ValueError):
            rw.compute(cfg, 0.9, 0.9, 0.0, rw.RUNNING)

    def test_no_progress_is_terminal_failure(self):
        env, game = make_env()
        tr = run(env, lambda i, e: COAST)             # never moves
        self.assertEqual(tr[-1].status, rw.ABANDONED)
        self.assertTrue(tr[-1].terminated)
        self.assertEqual(tr[-1].race_ms, 5000)
        self.assertEqual(tr[-1].reward_components["finish"], 0.0)
        self.assertEqual(game.sent[-1], "REL")

    def test_time_limit_is_truncation_not_terminal(self):
        env, game = make_env(SyntheticGame(accel=0.3), time_limit_ms=3000)
        tr = run(env, lambda i, e: GAS)
        last = tr[-1]
        self.assertEqual(last.status, rw.TIME_LIMIT)
        self.assertTrue(last.truncated and not last.terminated)
        self.assertGreater(last.discount, 0.0)       # the learner bootstraps
        self.assertEqual(last.race_ms, 3000)
        self.assertEqual(game.sent[-1], "REL")

    def test_technical_errors_invalidate_release_and_require_reset(self):
        for fault in ("silence", "released", "stale", "nan", "uid", "cp_drop", "fake_finish",
                      "wrong_action", "disconnect"):
            with self.subTest(fault=fault):
                env, game = make_env()
                env.reset()
                env.step(GAS)
                game.fault = fault
                t = env.step(GAS)
                self.assertFalse(t.valid)
                self.assertEqual(t.status, ERROR)
                self.assertIsNone(t.reward)
                self.assertIsNone(t.next_obs)
                self.assertTrue(t.done)
                if fault != "disconnect":
                    self.assertEqual(game.sent[-1], "REL")
                with self.assertRaises(EnvUsageError):
                    env.step(GAS)
                game.fault = None
                env.reset()                           # recovery through a new episode
                self.assertTrue(env.step(GAS).valid)

    def test_reset_to_a_wrong_map_is_refused(self):
        env, _ = make_env(SyntheticGame(uid="OTHER"))
        with self.assertRaises(BridgeError):
            env.reset()
        self.assertFalse(env.ready)


class RewardDecomposition(unittest.TestCase):
    def test_components_sum_and_version_hash(self):
        cfg = rw.RewardConfig()
        b = rw.compute(cfg, 0.10, 0.11, 0.05, rw.RUNNING)
        self.assertAlmostEqual(b.total, b.progress + b.time + b.finish)
        self.assertAlmostEqual(b.time, -0.05)
        self.assertAlmostEqual(b.progress, cfg.gamma(0.05) * 11.0 - 10.0)
        d = cfg.to_dict()
        self.assertEqual(d["schema"], rw.REWARD_SCHEMA)
        self.assertNotEqual(d["sha256"], rw.RewardConfig(finish_bonus=50.0).to_dict()["sha256"])
        with self.assertRaises(ValueError):
            rw.RewardConfig(discount_per_second=1.5)
        with self.assertRaises(ValueError):
            rw.compute(cfg, 0.1, float("nan"), 0.05, rw.RUNNING)

    def test_shaping_telescopes_on_terminated_episodes(self):
        cfg = rw.RewardConfig(time_cost_per_s=0.0, finish_bonus=0.0)
        env, _ = make_env(reward_cfg=cfg)
        tr = run(env, lambda i, e: GAS)
        self.assertEqual(tr[-1].status, rw.FINISHED)
        # Phi(terminal) = 0: the shaping return from s0 equals -Phi(s0), whatever the path.
        phi0 = cfg.potential(env.tracker.line.s[0] / env.tracker.line.length)
        self.assertAlmostEqual(ret(tr), -phi0, delta=1e-6)


class AntiExploitation(unittest.TestCase):
    """REWARDS §5, on SYNTHETIC scenarios."""

    def test_faster_valid_run_is_preferred(self):
        fast = ret(run(make_env(SyntheticGame(accel=10.0))[0], lambda i, e: GAS))
        slow = ret(run(make_env(SyntheticGame(accel=6.0))[0], lambda i, e: GAS))
        self.assertGreater(fast, slow)

    def test_back_and_forth_gives_no_exploitable_gain(self):
        # forward 2 s then brake/reverse back to the start, repeated, until the abandon rule
        def pol(i, e):
            return GAS if (i // 40) % 2 == 0 else BRAKE
        env, _ = make_env()
        tr = run(env, pol)
        self.assertGreater(max(t.info["s_m"] for t in tr), 10.0)
        straight_run = ret(run(make_env()[0], lambda i, e: GAS))
        self.assertLess(ret(tr), straight_run)
        self.assertLess(ret(tr), 0.0)
        # every forward+back cycle returns at most 0 shaping
        cfg = rw.RewardConfig()
        g = cfg.gamma(0.05)
        loop = [rw.compute(cfg, p, q, 0.05, rw.RUNNING) for p, q in
                [(0.1, 0.2), (0.2, 0.3), (0.3, 0.2), (0.2, 0.1)]]
        self.assertLessEqual(sum(b.progress * g ** k for k, b in enumerate(loop)), 1e-12)

    def test_oscillating_around_a_checkpoint_pays_nothing_repeatedly(self):
        cfg = rw.RewardConfig(time_cost_per_s=0.0)
        cp = 100.0 / LENGTH
        steps = [rw.compute(cfg, cp - 0.01, cp + 0.01, 0.05, rw.RUNNING),
                 rw.compute(cfg, cp + 0.01, cp - 0.01, 0.05, rw.RUNNING)] * 20
        self.assertLessEqual(rw.discounted_return(steps), 0.0)
        self.assertTrue(all(b.finish == 0.0 for b in steps))

    def test_crossing_projection_cannot_jump_to_a_future_portion(self):
        # SYNTHETIC overpass line: the lower road (x=0, y=0, s = z for z <= 200) passes under
        # a future part of the line (y=5, crossing above z=200, s ~ 713). The car drives on the
        # lower road under the deck; the game still counts 0 checkpoints.
        env, game = make_env(SyntheticGame(cp_at=(1e9, 1e9)),
                             prepared=synthetic_prepared(figure_with_overpass()))
        env.reset()
        seen = []
        while game.z < 200.0:
            t = env.step(GAS)
            self.assertTrue(t.valid)
            seen.append((game.z, t.info["s_m"], t.reward_components["progress"]))
        self.assertTrue(all(abs(s - z) < 1.0 for z, s, _ in seen), seen[-3:])
        self.assertLess(max(p for *_, p in seen), 2.0)

    def test_relocalization_is_bounded_by_the_game_checkpoint_sector(self):
        # SYNTHETIC teleport (a respawn-like jump; never produced by the env reset) onto the
        # upper deck, a future sector: the tracker may relocalize, but only inside sector 0.
        env, game = make_env(SyntheticGame(cp_at=(1e9, 1e9)),
                             prepared=synthetic_prepared(figure_with_overpass()))
        env.reset()
        env.step(GAS)
        game.teleport = [0.0, 5.0, 200.0]
        t = env.step(GAS)
        self.assertTrue(t.valid and t.info["relocalized"])
        self.assertLessEqual(t.info["s_m"], env.tracker.sector_range(0)[2] + 1e-6)

    def test_missed_checkpoint_gives_no_valid_finish(self):
        env, game = make_env(SyntheticGame(cp_at=(100.0, 1e9)))    # second CP never reached
        tr = run(env, lambda i, e: GAS, max_steps=400)
        self.assertNotIn(rw.FINISHED, [t.status for t in tr])
        self.assertTrue(all(t.reward_components is None or t.reward_components["finish"] == 0.0
                            for t in tr))
        env, game = make_env()
        env.reset()
        game.fault = "fake_finish"                    # finish flag without 3/3 checkpoints
        self.assertEqual(env.step(GAS).status, ERROR)

    def test_reset_is_never_a_rewarded_transition(self):
        env, game = make_env()
        run(env, lambda i, e: GAS, max_steps=60)
        n_before = len([line for line in game.sent if line.startswith("A ")])
        env.reset()
        t = env.step(GAS)
        self.assertEqual(t.action_id, 1)
        self.assertEqual(t.race_ms, 50)
        self.assertLess(abs(t.reward_components["progress"]), 1.0)   # no jump across episodes
        self.assertEqual(n_before + 1, len([line for line in game.sent if line.startswith("A ")]))

    def test_early_abandon_never_beats_a_slow_admissible_finish(self):
        cfg = rw.RewardConfig()
        rules = EpisodeRules.from_profile(PROFILE)
        cal = rw.check_calibration(cfg, rules.time_limit_ms / 1000, rules.no_progress_ms / 1000)
        self.assertTrue(cal["ok"], cal)
        # Slowest finishing synthetic car inside the time limit vs abandoning at any point.
        slow_env, _ = make_env(SyntheticGame(accel=0.6))
        slow = run(slow_env, lambda i, e: GAS)
        self.assertEqual(slow[-1].status, rw.FINISHED)
        slow_ret = ret(slow)
        for stop_after in (0, 20, 60, 100):     # 100 steps: stops near 170 m of 300 m
            def pol(i, e, k=stop_after):
                return GAS if i < k else BRAKE if e.last_state["velocity"][2] > 0 else COAST
            ab = run(make_env()[0], pol)
            self.assertEqual(ab[-1].status, rw.ABANDONED)
            self.assertLess(ret(ab), slow_ret, stop_after)

    def test_prolonged_immobility_does_not_pay(self):
        env, _ = make_env()
        idle = run(env, lambda i, e: COAST)
        self.assertEqual(idle[-1].status, rw.ABANDONED)
        self.assertLess(ret(idle), 0.0)
        self.assertTrue(all(t.reward < 0 for t in idle))
        self.assertLess(ret(idle), ret(run(make_env()[0], lambda i, e: GAS)))

    def test_contacts_and_sliding_are_never_penalized(self):
        a_env, a_game = make_env()
        b_env, b_game = make_env()
        b_game.contact, b_game.sliding = [False, True, False, True], [True] * 4
        a, b = run(a_env, lambda i, e: GAS), run(b_env, lambda i, e: GAS)
        self.assertEqual([t.reward for t in a], [t.reward for t in b])
        self.assertNotEqual(a[5].next_obs, b[5].next_obs)   # observed, not rewarded

    def test_cadence_change_keeps_time_cost_and_per_second_discount(self):
        r5 = run(make_env(ticks=5)[0], lambda i, e: Action(0.0, True, False, 5))
        r10 = run(make_env(ticks=10)[0], lambda i, e: Action(0.0, True, False, 10))
        self.assertEqual(r5[-1].race_ms, r10[-1].race_ms)
        t5 = sum(t.reward_components["time"] for t in r5)
        t10 = sum(t.reward_components["time"] for t in r10)
        self.assertAlmostEqual(t5, t10, places=9)
        cfg = rw.RewardConfig()
        self.assertAlmostEqual(cfg.gamma(0.05) ** 2, cfg.gamma(0.10))
        self.assertAlmostEqual(ret(r5), ret(r10), delta=0.5)

    def test_disconnect_rejects_the_transition(self):
        env, game = make_env()
        env.reset()
        game.fault = "disconnect"
        t = env.step(GAS)
        self.assertFalse(t.valid)
        self.assertIn("transport", t.info["error"])

    def test_time_limit_status_and_future_value_are_explicit(self):
        env, _ = make_env(SyntheticGame(accel=0.3), time_limit_ms=2000)
        last = run(env, lambda i, e: GAS)[-1]
        self.assertEqual((last.status, last.terminated, last.truncated),
                         (rw.TIME_LIMIT, False, True))
        self.assertAlmostEqual(last.discount, rw.RewardConfig().gamma(0.05))
        self.assertNotEqual(last.reward_components["progress"],
                            -rw.RewardConfig().potential(last.info["progress"]))


V2 = rw.RewardConfig(progress_mode="delta", finish_bonus=20.0, discount_per_second=0.905)


class RewardV2Delta(unittest.TestCase):
    """reward/2 (progress paid directly, J4-07), on SYNTHETIC scenarios."""

    def test_v1_hash_is_unchanged_and_v2_is_a_new_schema(self):
        # sha256 recorded by the reward/1 runs of J4 (night run of 2026-09-30)
        self.assertEqual(rw.RewardConfig().to_dict()["sha256"],
                         "7db1d3d8432464d38a294bd2384a05aa24d0f3e83752bbeb0557665c148588f3")
        self.assertEqual(V2.to_dict()["schema"], rw.REWARD_SCHEMA_V2)
        with self.assertRaises(ValueError):
            rw.RewardConfig(progress_mode="speed")

    def test_progress_is_paid_and_kept_on_abandon(self):
        b = rw.compute(V2, 0.10, 0.11, 0.05, rw.ABANDONED)
        self.assertAlmostEqual(b.progress, 1.0)
        self.assertEqual(b.discount, 0.0)
        pol = lambda i, e: GAS if i < 60 else BRAKE if e.last_state["velocity"][2] > 0 else COAST
        tr = run(make_env(reward_cfg=V2)[0], pol)
        self.assertEqual(tr[-1].status, rw.ABANDONED)
        paid = sum(t.reward_components["progress"] for t in tr)
        self.assertGreater(paid, 10.0)                                      # not clawed back
        self.assertAlmostEqual(paid, 100.0 * tr[-1].info["progress"], delta=1.0)  # start ~ 0

    def test_driving_even_slowly_beats_stopping_until_the_abandon(self):
        stop = ret(run(make_env(reward_cfg=V2)[0], lambda i, e: COAST))
        for accel in (0.6, 8.0):
            drive = ret(run(make_env(SyntheticGame(accel=accel), reward_cfg=V2)[0], lambda i, e: GAS))
            self.assertGreater(drive, stop, accel)
        # A01 calibration: the slowest pace that still beats stopping is far below any race
        pace = rw.break_even_pace(V2, EpisodeRules.from_profile(PROFILE).no_progress_ms / 1000)
        self.assertLess(pace * 160, 1.0)          # a 160 s lap is already worth driving

    def test_stopping_midway_never_beats_finishing(self):
        full = ret(run(make_env(reward_cfg=V2)[0], lambda i, e: GAS))
        for k in (20, 60, 100):
            pol = lambda i, e, k=k: GAS if i < k else BRAKE if e.last_state["velocity"][2] > 0 else COAST
            self.assertLess(ret(run(make_env(reward_cfg=V2)[0], pol)), full, k)

    def test_faster_finish_is_preferred(self):
        fast = ret(run(make_env(SyntheticGame(accel=10.0), reward_cfg=V2)[0], lambda i, e: GAS))
        slow = ret(run(make_env(SyntheticGame(accel=6.0), reward_cfg=V2)[0], lambda i, e: GAS))
        self.assertGreater(fast, slow)

    def test_back_and_forth_pays_nothing(self):
        steps = [rw.compute(V2, p, q, 0.05, rw.RUNNING) for p, q in
                 [(0.1, 0.2), (0.2, 0.3), (0.3, 0.2), (0.2, 0.1)]] * 10
        self.assertAlmostEqual(sum(b.progress for b in steps), 0.0)
        self.assertLess(rw.discounted_return(steps), 0.0)
        pol = lambda i, e: GAS if (i // 40) % 2 == 0 else BRAKE
        straight_run = ret(run(make_env(reward_cfg=V2)[0], lambda i, e: GAS))
        self.assertLess(ret(run(make_env(reward_cfg=V2)[0], pol)), straight_run)


if __name__ == "__main__":
    unittest.main()
