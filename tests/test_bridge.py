"""Synthetic transport tests for BridgeClient against a fake local server.

The fake server imitates the message shapes of plugins/TrackmaniaRLBridge.as.
It does NOT validate the TMInterface integration; see docs/reports/J1-integration.md.
"""
import json
import socket
import threading
import unittest

from trackmania_rl.bridge import BridgeClient, BridgeError
from trackmania_rl.protocol import Action


class FakeGame(threading.Thread):
    def __init__(self, script):
        super().__init__(daemon=True)
        self.server = socket.socket()
        self.server.bind(("127.0.0.1", 0))
        self.server.listen(1)
        self.port = self.server.getsockname()[1]
        self.script = script
        self.received = []

    def run(self):
        conn, _ = self.server.accept()
        with conn, conn.makefile("rwb", buffering=0) as f:
            f.write(b'{"kind":"hello","bridge_version":"fake"}\n')
            self.script(f, self.received)
        self.server.close()


def send(f, obj):
    f.write((json.dumps(obj) + "\n").encode())


class BridgeClientTests(unittest.TestCase):
    def test_step_returns_state_for_its_own_action_only(self):
        def script(f, received):
            received.append(f.readline())
            # stale state from a previous action, then an event, then the right one
            send(f, {"kind": "state", "reason": "boundary", "episode": 1, "action_id": 6})
            send(f, {"kind": "event", "event": "checkpoint", "current": 1})
            send(f, {"kind": "state", "reason": "boundary", "episode": 1, "action_id": 7,
                     "tick_ms": 50})
            received.append(f.readline())

        game = FakeGame(script); game.start()
        client = BridgeClient(port=game.port)
        client.connect()
        state = client.step(1, 7, 3, Action(-0.5, True, True, ticks=5))
        self.assertEqual(state["action_id"], 7)
        self.assertGreaterEqual(state["_latency_s"], 0)
        self.assertTrue(any(m.get("event") == "checkpoint" for m in client.pending))
        client.close()
        game.join(2)
        self.assertEqual(game.received[0], b"A 1 7 3 -32768 1 1 5\n")
        self.assertEqual(game.received[1], b"REL\n")

    def test_release_by_game_invalidates_the_transition(self):
        def script(f, received):
            received.append(f.readline())
            send(f, {"kind": "event", "event": "released", "reason": "action_timeout"})
            f.readline()

        game = FakeGame(script); game.start()
        client = BridgeClient(port=game.port)
        client.connect()
        with self.assertRaises(BridgeError):
            client.step(1, 1, 0, Action(0.0, True, False))
        client.close()

    def test_silence_and_disconnect_raise(self):
        def script(f, received):
            received.append(f.readline())  # then close without answering

        game = FakeGame(script); game.start()
        client = BridgeClient(port=game.port)
        client.connect()
        with self.assertRaises(BridgeError):
            client.step(1, 1, 0, Action(0.0, False, False), timeout=1.0)
        client.close()

    def test_auto_restart_is_an_optional_fifth_cfg_field(self):
        def script(f, received):
            for _ in range(2):
                line = f.readline()
                received.append(line)
                send(f, {"kind": "event", "event": "config", "sync": True, "stream_every": 0,
                         "auto_restart": line.strip().endswith(b" 1")})

        game = FakeGame(script); game.start()
        client = BridgeClient(port=game.port)
        client.connect()
        self.assertFalse(client.configure(True, 1000, 0)["auto_restart"])
        self.assertTrue(client.configure(True, 1000, 0, auto_restart=True)["auto_restart"])
        client.close()
        game.join(2)
        self.assertEqual(game.received, [b"CFG 1 1000 0\n", b"CFG 1 1000 0 1\n"])

    def test_official_finish_is_a_sixth_cfg_field_and_must_be_confirmed(self):
        def script(f, received):
            for confirmed in (True, False):
                received.append(f.readline())
                send(f, {"kind": "event", "event": "config", "sync": True, "stream_every": 0,
                         "auto_restart": False, "official_finish": confirmed})

        game = FakeGame(script); game.start()
        client = BridgeClient(port=game.port)
        client.connect()
        self.assertTrue(client.configure(True, 1000, 0, official_finish=True)["official_finish"])
        with self.assertRaisesRegex(BridgeError, "official_finish"):
            client.configure(True, 1000, 0, official_finish=True)   # old bridge ignores it
        with self.assertRaises(ValueError):
            client.configure(True, 1000, 0, auto_restart=True, official_finish=True)
        client.close()
        game.join(2)
        self.assertEqual(game.received, [b"CFG 1 1000 0 0 1\n", b"CFG 1 1000 0 0 1\n"])

    def test_reset_fails_fast_when_the_plugin_cannot_restart(self):
        for event in ({"event": "reset_requested", "method": "none_not_in_race"},
                      {"event": "rewind_failed", "why": "no_start_state"}):
            def script(f, received, event=event):
                received.append(f.readline())
                send(f, {"kind": "event", "episode": 4, **event})
                f.readline()

            game = FakeGame(script); game.start()
            client = BridgeClient(port=game.port)
            client.connect()
            with self.assertRaisesRegex(BridgeError, "restart impossible"):
                client.reset(4, timeout=2.0)
            client.close()
            game.join(2)
            self.assertEqual(game.received[0], b"R 4\n")

    def test_reset_after_finish_waits_for_the_start_state(self):
        def script(f, received):
            received.append(f.readline())
            send(f, {"kind": "event", "event": "reset_requested", "method": "rewind_start",
                     "episode": 5})
            send(f, {"kind": "event", "event": "rewound", "cause": "reset_after_finish",
                     "episode": 5})
            send(f, {"kind": "state", "reason": "start", "episode": 5, "race_ms": 0})
            f.readline()

        game = FakeGame(script); game.start()
        client = BridgeClient(port=game.port)
        client.connect()
        self.assertEqual(client.reset(5, timeout=2.0)["race_ms"], 0)
        client.close()


if __name__ == "__main__":
    unittest.main()
