"""J6 command bursts: synthetic arrays only (no game)."""
import types
import unittest

import numpy as np

from trackmania_rl.training import command_burst, validate_command_bursts


class CommandBurstTest(unittest.TestCase):
    def test_burst_overrides_command_only(self):
        cfg = {"start_prob": 0.999, "min_steps": 2, "max_steps": 2, "commands": [0], "seed": 3}
        model = types.SimpleNamespace()
        for _ in range(4):
            a = np.array([[0.3, -1, 1, -1, -1]], np.float32)
            b = a.copy()
            command_burst(model, cfg, a, b)
            self.assertAlmostEqual(float(a[0, 0]), 0.3, places=6)
            self.assertTrue(np.array_equal(a, b))
            self.assertEqual(list(a[0, 1:]), [1, -1, -1, -1])    # coast
        self.assertEqual(model._burst_steps, 4)

    def test_validation(self):
        for bad in ({"start_prob": 0.02, "min_steps": 3, "max_steps": 1, "commands": [0]},
                    {"start_prob": 0.02, "min_steps": 1, "max_steps": 2, "commands": [5]},
                    {"start_prob": 0.02, "min_steps": 1, "max_steps": 2, "commands": [0], "x": 1}):
            with self.assertRaises(ValueError):
                validate_command_bursts(bad)


if __name__ == "__main__":
    unittest.main()
