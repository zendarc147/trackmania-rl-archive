"""Python side of the J1 TMInterface bridge (plugins/TrackmaniaRLBridge.as).

Transport only: connect, frame messages, send commands, match states to actions.
No driving strategy lives here.
"""
from __future__ import annotations

import json
import socket
import time
from collections import deque
from typing import Callable

from .protocol import Action, Decoder

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8479


class BridgeError(RuntimeError):
    """Connection lost, timeout or protocol violation; the transition is invalid."""


class BridgeClient:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT,
                 trace: Callable[[str, dict], None] | None = None):
        self.host, self.port = host, port
        self.sock: socket.socket | None = None
        self.decoder = Decoder()
        self.pending: deque[dict] = deque()
        self.trace = trace or (lambda direction, record: None)
        self.hello: dict | None = None

    # -- connection -------------------------------------------------------
    def connect(self, timeout: float = 5.0) -> dict:
        self.sock = socket.create_connection((self.host, self.port), timeout=timeout)
        self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        self.hello = self.wait_for(lambda m: m["kind"] == "hello", timeout)
        return self.hello

    def close(self, release: bool = True) -> None:
        """Release inputs (best effort) then close. Always leaves the socket closed."""
        if self.sock is None:
            return
        try:
            if release:
                self.send_line("REL")
        except OSError:
            pass
        finally:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- low level --------------------------------------------------------
    def send_line(self, line: str) -> float:
        if self.sock is None:
            raise BridgeError("not connected")
        data = (line.rstrip("\n") + "\n").encode("ascii")
        stamp = time.monotonic()
        self.trace("tx", {"line": line, "mono": stamp})
        try:
            self.sock.sendall(data)
        except OSError as exc:
            raise BridgeError(f"send failed: {exc}") from exc
        return stamp

    def _read_some(self, deadline: float) -> None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise BridgeError("timeout")
        self.sock.settimeout(remaining)
        try:
            data = self.sock.recv(65536)
        except socket.timeout as exc:
            raise BridgeError("timeout") from exc
        except OSError as exc:
            raise BridgeError(f"recv failed: {exc}") from exc
        if not data:
            raise BridgeError("connection closed by game")
        now = time.monotonic()
        for record in self.decoder.feed(data):
            record["_rx_mono"] = now
            self.trace("rx", record)
            self.pending.append(record)

    def wait_for(self, predicate: Callable[[dict], bool], timeout: float) -> dict:
        """Return the first message matching predicate; others stay queued."""
        if self.sock is None:
            raise BridgeError("not connected")
        deadline = time.monotonic() + timeout
        while True:
            for i, record in enumerate(self.pending):
                if predicate(record):
                    del self.pending[i]
                    return record
            self._read_some(deadline)

    def drain(self, duration: float) -> list[dict]:
        """Collect every message for duration seconds (diagnostics)."""
        end = time.monotonic() + duration
        out = list(self.pending)
        self.pending.clear()
        while time.monotonic() < end:
            try:
                self._read_some(min(end, time.monotonic() + 0.05))
            except BridgeError as exc:
                if str(exc) != "timeout":
                    raise
            out.extend(self.pending)
            self.pending.clear()
        return out

    # -- commands ---------------------------------------------------------
    def configure(self, sync: bool, timeout_ms: int, stream_every: int,
                  auto_restart: bool = False, official_finish: bool = False) -> dict:
        """Official finish (bridge >= 0.4.0) cannot be combined with auto restart."""
        if auto_restart and official_finish:
            raise ValueError("official_finish conflicts with auto_restart")
        line = f"CFG {int(sync)} {int(timeout_ms)} {int(stream_every)}"
        if official_finish:
            line += " 0 1"
        elif auto_restart:
            line += " 1"
        self.send_line(line)
        event = self.wait_for(lambda m: m.get("event") == "config", 2.0)
        if official_finish and event.get("official_finish") is not True:
            raise BridgeError("bridge does not support official_finish (needs >= 0.4.0)")
        return event

    def reset(self, episode: int, timeout: float = 15.0) -> dict:
        """Restart the race and return the first state at race time >= 0."""
        self.send_line(f"R {episode}")

        def match(m: dict) -> bool:
            if m.get("episode") == episode:
                if m.get("event") == "reset_requested" and str(m.get("method", "")).startswith("none"):
                    raise BridgeError(f"restart impossible: {m.get('method')}")
                if m.get("event") == "rewind_failed":
                    raise BridgeError(f"restart impossible: rewind failed ({m.get('why')})")
            return m["kind"] == "state" and m.get("reason") == "start" and m["episode"] == episode

        return self.wait_for(match, timeout)

    def step(self, episode: int, action_id: int, source_seq: int, action: Action,
             timeout: float = 2.0) -> dict:
        """Send one action; return the boundary state produced by exactly that action."""
        sent = self.send_line(action.encode(episode=episode, action_id=action_id,
                                            source_seq=source_seq).decode("ascii").strip())

        def match(m: dict) -> bool:
            if m.get("event") == "action_rejected":
                raise BridgeError(f"action rejected: {m}")
            if m.get("event") == "released" and m.get("reason") != "client_request":
                raise BridgeError(f"inputs released by game: {m.get('reason')}")
            return (m["kind"] == "state" and m.get("reason") in ("boundary", "finish")
                    and m["episode"] == episode and m["action_id"] == action_id)

        state = self.wait_for(match, timeout)
        state["_latency_s"] = state["_rx_mono"] - sent
        return state

    def set_speed(self, factor: float, timeout: float = 2.0) -> dict:
        """Simulation speed (bridge >= 0.3.0, SimulationManager.SetSpeed). The plugin restores
        speed 1 when this client is lost or replaced; callers still reset it to 1 on exit."""
        self.send_line(f"SPD {float(factor):g}")
        ev = self.wait_for(lambda m: m.get("event") in ("speed", "unknown_command"), timeout)
        if ev.get("event") != "speed" or ev.get("ok") is not True:
            raise BridgeError(f"speed {factor} refused (bridge >= 0.3.0 needed): {ev}")
        return ev

    def ping(self, n: int, timeout: float = 2.0) -> float:
        sent = self.send_line(f"PING {n}")
        reply = self.wait_for(lambda m: m.get("event") == "pong" and m.get("n") == n, timeout)
        return reply["_rx_mono"] - sent


def jsonl_tracer(path):
    handle = open(path, "a", encoding="utf-8")

    def trace(direction: str, record: dict) -> None:
        handle.write(json.dumps({"dir": direction, **record}, separators=(",", ":")) + "\n")
        handle.flush()

    trace.close = handle.close  # type: ignore[attr-defined]
    return trace
