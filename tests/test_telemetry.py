"""Synthetic state and transition tests; no claim of live validation."""
import unittest
from trackmania_rl import protocol


def state(seq=1, tick=100, **changes):
    value = dict(kind="state", version=1, episode=1, seq=seq, tick_ms=tick,
                 race_ms=tick, wall_ms=tick, map_uid="synthetic", action_id=0,
                 position=[0., 0., 0.], velocity=[0., 0., 0.],
                 rotation_ypr=[0., 0., 0.], angular_velocity=[0., 0., 0.],
                 gear=1, turning_rate=0., wheel_contact=[True]*4,
                 wheel_sliding=[False]*4, wheel_offsets=[[0., 0., 0.]]*4,
                 car_inputs=[0., 0., 0.], inputs=[0, 0, 0],
                 checkpoints=0, finished=False)
    value.update(changes)
    return value


class TelemetryTests(unittest.TestCase):
    def test_missing_nonfinite_and_malformed_observations_are_rejected(self):
        self.assertTrue(hasattr(protocol, 'validate_state'), 'state validation missing')
        protocol.validate_state(state())
        bad = state(); del bad['velocity']
        for sample in (bad, state(velocity=[float('inf'), 0, 0]),
                       state(wheel_contact=[True]*3), state(gear=True),
                       state(rotation_ypr=[0, 0]), state(version=2)):
            with self.subTest(sample=sample), self.assertRaises(ValueError):
                protocol.validate_state(sample)


if __name__ == '__main__':
    unittest.main()
