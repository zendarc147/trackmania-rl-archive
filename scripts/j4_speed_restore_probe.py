"""Live check of bridge 0.3.0 safety: speed goes back to 1 when the client disappears.

Sets speed x4 (no action sent, the car is not controlled), closes the socket abruptly
without restoring the speed, reconnects and reads the speed in the hello message.

Usage: uv run python scripts/j4_speed_restore_probe.py
"""
from __future__ import annotations

import json
import pathlib
import socket
import struct
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trackmania_rl.bridge import BridgeClient  # noqa: E402


def main() -> int:
    b = BridgeClient()
    h0 = b.connect()
    ev = b.set_speed(4.0)
    b.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    b.sock.close()          # abrupt close, no REL, no SPD 1
    b.sock = None
    time.sleep(1.5)         # the plugin notices on its next heartbeat write (500 ms)
    b2 = BridgeClient()
    h1 = b2.connect()
    b2.close(release=False)
    out = {"speed_before": h0.get("speed"), "speed_set": ev.get("speed_variable"),
           "speed_after_reconnect": h1.get("speed"), "bridge": h1.get("bridge_version"),
           "restored": h1.get("speed") == 1.0}
    print(json.dumps(out))
    return 0 if out["restored"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
