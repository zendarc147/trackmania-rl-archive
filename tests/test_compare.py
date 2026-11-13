"""Off-game tests for the run comparison (D25). SYNTHETIC run directories only."""
import json
import pathlib
import tempfile
import unittest

from trackmania_rl.compare import compare_runs, trend


def make_run(root, name, codec, seed, episodes, timesteps):
    d = pathlib.Path(root) / name
    d.mkdir()
    (d / "config.json").write_text(json.dumps({"config": {
        "name": name, "action_codec": codec, "seed": seed,
        "budget": {"transitions": timesteps}, "sac": {"batch_size": 256}, "reward": {}}}))
    (d / "status.json").write_text(json.dumps({"timesteps": timesteps, "phase": "finished_budget"}))
    with open(d / "episodes.jsonl", "w") as f:
        for e in episodes:
            f.write(json.dumps(e) + "\n")
    return d


def ep(ts, status, progress, finish=None):
    return {"timesteps": ts, "status": status, "progress_max": progress, "finish_ms": finish,
            "return": progress * 100}


class CompareRuns(unittest.TestCase):
    def test_equal_budget_window_and_differences(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = make_run(tmp, "a", "threshold_v1", 1,
                         [ep(100, "abandoned", 0.1), ep(250, "finished", 1.0, 31000),
                          ep(400, "finished", 1.0, 29000)], 400)
            b = make_run(tmp, "b", "hybrid4_v1", 1,
                         [ep(150, "abandoned", 0.2), ep(300, "abandoned", 0.3)], 300)
            out = compare_runs([a, b], last_fraction=1.0)
            self.assertEqual(out["common_transitions"], 300)
            ra, rb = out["runs"]
            # the episode ending at 400 is beyond the common budget: excluded
            self.assertEqual(ra["episodes"], 2)
            self.assertEqual(ra["finishes"], 1)
            self.assertEqual(ra["best_finish_ms"], 31000)
            self.assertEqual(rb["finishes"], 0)
            self.assertIsNone(rb["best_finish_ms"])
            self.assertEqual(out["differences"], ["action_codec"])
            self.assertFalse(out["controlled"])      # one run, one seed per arm

    def test_other_differences_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = make_run(tmp, "a", "threshold_v1", 1, [ep(10, "abandoned", 0.1)], 10)
            b = make_run(tmp, "b", "hybrid4_v1", 2, [ep(10, "abandoned", 0.1)], 10)
            self.assertEqual(compare_runs([a, b])["differences"], ["action_codec", "seed"])

    def test_controlled_with_two_seeds_per_arm(self):
        # D25 protocol: each arm run twice with different seeds. seed differs
        # between runs by design and must not block "controlled".
        with tempfile.TemporaryDirectory() as tmp:
            a1 = make_run(tmp, "a1", "threshold_v1", 1, [ep(10, "abandoned", 0.1)], 10)
            a2 = make_run(tmp, "a2", "threshold_v1", 2, [ep(10, "abandoned", 0.1)], 10)
            b1 = make_run(tmp, "b1", "hybrid4_v1", 1, [ep(10, "abandoned", 0.1)], 10)
            b2 = make_run(tmp, "b2", "hybrid4_v1", 2, [ep(10, "abandoned", 0.1)], 10)
            out = compare_runs([a1, b1, a2, b2])
            self.assertEqual(out["differences"], ["action_codec", "seed"])
            self.assertTrue(out["controlled"])

    def test_not_controlled_when_other_key_also_differs(self):
        # seed alone must not "hide" a real confound like reward.
        with tempfile.TemporaryDirectory() as tmp:
            a1 = make_run(tmp, "a1", "threshold_v1", 1, [ep(10, "abandoned", 0.1)], 10)
            a2 = make_run(tmp, "a2", "threshold_v1", 2, [ep(10, "abandoned", 0.1)], 10)
            b1 = make_run(tmp, "b1", "hybrid4_v1", 1, [ep(10, "abandoned", 0.1)], 10)
            d = pathlib.Path(b1)
            cfg = json.loads((d / "config.json").read_text())
            cfg["config"]["reward"] = {"bonus": 999}
            (d / "config.json").write_text(json.dumps(cfg))
            b2 = make_run(tmp, "b2", "hybrid4_v1", 2, [ep(10, "abandoned", 0.1)], 10)
            out = compare_runs([a1, b1, a2, b2])
            self.assertIn("reward", out["differences"])
            self.assertFalse(out["controlled"])


class Trend(unittest.TestCase):
    def _run(self, tmp, name, learning):
        eps = []
        for i in range(50):
            f = i / 49 if learning else 0.0
            e = ep(100 * (i + 1), "abandoned", 0.1 + 0.5 * f)
            e.update(episode=i + 1, steer_abs_mean=0.5 - 0.2 * f, action_share={
                "coast": 0.25 - 0.15 * f, "gas": 0.25 + 0.45 * f,
                "brake": 0.25 - 0.15 * f, "gas_brake": 0.25 - 0.15 * f})
            eps.append(e)
        return make_run(tmp, name, "hybrid4_v1", 1, eps, 5000)

    def test_random_driving_is_flagged_and_learning_is_seen(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertTrue(trend(self._run(tmp, "r", False))["verdict"].startswith("no sign"))
            out = trend(self._run(tmp, "l", True))
            self.assertEqual(out["verdict"], "signs of learning")
            self.assertEqual(len(out["slices"]), 5)


if __name__ == "__main__":
    unittest.main()
