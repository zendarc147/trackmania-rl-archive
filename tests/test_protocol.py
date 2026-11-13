"""Synthetic protocol tests. These do not validate TMInterface integration."""
import importlib.util
import unittest


class ActionTests(unittest.TestCase):
    def test_normalized_action_encodes_progressive_steer_and_binary_pedals(self):
        self.assertIsNotNone(importlib.util.find_spec("trackmania_rl"), "J1 package missing")
        from trackmania_rl.protocol import Action

        action = Action(0.25, True, False, ticks=5)
        self.assertEqual(action.encode(episode=2, action_id=7, source_seq=31),
                         b"A 2 7 31 16384 1 0 5\n")

    def test_invalid_actions_rejected_before_transmission(self):
        from trackmania_rl.protocol import Action
        for values in ((float('nan'), True, False, 5), (1.01, True, False, 5),
                       (0, 0.5, False, 5), (0, True, False, 0),
                       (0, True, False, 26), (0, True, False, True)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                Action(*values)


class FramingTests(unittest.TestCase):
    def test_fragmented_and_coalesced_json_lines(self):
        from trackmania_rl import protocol
        self.assertTrue(hasattr(protocol, 'Decoder'), 'bounded decoder missing')
        decoder = protocol.Decoder()
        self.assertEqual(decoder.feed(b'{"kind":"sta'), [])
        self.assertEqual(decoder.feed(b'te"}\n{"kind":"idle"}\n'),
                         [{'kind': 'state'}, {'kind': 'idle'}])
        for data in (b'x' * 16385, b'{"x":NaN}\n', b'[]\n', b'\xff\n'):
            with self.subTest(data=data[:20]), self.assertRaises(ValueError):
                protocol.Decoder().feed(data)


if __name__ == "__main__":
    unittest.main()
