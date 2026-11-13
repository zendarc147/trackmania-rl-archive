"""J1 live probe: exercise the TMInterface bridge in the real game.

Requires TMNF + TMInterface running with plugins/TrackmaniaRLBridge.as loaded and a
local race open. Every message is written to runs/j1/<stamp>/trace.jsonl.

This is a test controller with fixed open-loop actions: it is NOT a driving policy.

Usage: uv run python scripts/j1_live_probe.py [phase ...]
Phases: hello ping control timeout disconnect async stream
"""
from __future__ import annotations

import json
import pathlib
import socket
import statistics
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trackmania_rl.bridge import BridgeClient, BridgeError, jsonl_tracer  # noqa: E402
from trackmania_rl.protocol import Action  # noqa: E402

STAMP = time.strftime("%Y%m%d-%H%M%S")
OUT = ROOT / "runs" / "j1" / STAMP
OUT.mkdir(parents=True, exist_ok=True)
TRACE = jsonl_tracer(OUT / "trace.jsonl")
SUMMARY: dict = {"stamp": STAMP}


def log(msg: str) -> None:
    print(msg, flush=True)


def client() -> BridgeClient:
    c = BridgeClient(trace=TRACE)
    SUMMARY.setdefault("hello", c.connect())
    return c


def pct(values, q):
    values = sorted(values)
    return values[min(len(values) - 1, int(q * (len(values) - 1) + 0.5))]


def phase_hello():
    c = client()
    log(f"hello: {c.hello}")
    c.close()


def phase_ping():
    c = client()
    rtts = [c.ping(i) * 1000 for i in range(50)]
    SUMMARY["ping_ms"] = {"median": statistics.median(rtts), "p95": pct(rtts, .95),
                          "max": max(rtts)}
    log(f"ping ms: {SUMMARY['ping_ms']}")
    c.close()


SCRIPT = (  # (label, steps, action)
    [("gas", 30, Action(0.0, True, False, 5))]
    + [("steer_right_half", 10, Action(0.5, True, False, 5))]
    + [("steer_left_full", 10, Action(-1.0, True, False, 5))]
    + [("steer_ramp", 9, None)]
    + [("coast", 10, Action(0.0, False, False, 5))]
    + [("gas_and_brake", 10, Action(0.0, True, True, 5))]
    + [("brake", 20, Action(0.0, False, True, 5))]
)


def phase_control():
    c = client()
    c.configure(sync=True, timeout_ms=1000, stream_every=0)
    t0 = time.monotonic()
    start = c.reset(episode=1)
    log(f"reset -> start state race_ms={start['race_ms']} in {time.monotonic() - t0:.2f}s")
    rows, prev, aid = [], start, 0
    for label, n, action in SCRIPT:
        for k in range(n):
            if action is None:
                act = Action(-1.0 + 0.25 * k, True, False, 5)
            else:
                act = action
            aid += 1
            state = c.step(1, aid, prev["seq"], act)
            rows.append({"label": label, "action": [act.steer, act.accelerate, act.brake,
                                                    act.ticks],
                         "prev_tick": prev["tick_ms"], "tick": state["tick_ms"],
                         "applied_tick": state["applied_tick_ms"],
                         "latency_ms": state["_latency_s"] * 1000,
                         "wall_gap_ms": state["wall_ms"] - prev["wall_ms"],
                         "car_inputs": state["car_inputs"], "inputs": state["inputs"],
                         "turning_rate": state["turning_rate"],
                         "velocity": state["velocity"], "local_velocity": state["local_velocity"],
                         "gear": state["gear"], "speed": state["display_speed"],
                         "wheel_contact": state["wheel_contact"],
                         "wheel_sliding": state["wheel_sliding"], "seq": state["seq"],
                         "prev_seq": prev["seq"]})
            prev = state
    c.send_line("REL")
    rel = c.wait_for(lambda m: m.get("event") == "released", 2)
    (OUT / "control_rows.json").write_text(json.dumps(rows, indent=1))
    lat = [r["latency_ms"] for r in rows]
    dticks = sorted({r["tick"] - r["prev_tick"] for r in rows})
    SUMMARY["control"] = {"steps": len(rows), "latency_ms_median": statistics.median(lat),
                          "latency_ms_p95": pct(lat, .95), "latency_ms_max": max(lat),
                          "tick_deltas": dticks,
                          "seq_gaps": sorted({r["seq"] - r["prev_seq"] for r in rows}),
                          "release": rel}
    log(f"control: {SUMMARY['control']}")
    for label, *_ in SCRIPT:
        sel = [r for r in rows if r["label"] == label]
        last = sel[-1]
        log(f"  {label:17s} car_inputs={last['car_inputs']} inputs={last['inputs']} "
            f"TR={last['turning_rate']:.3f} speed={last['speed']} gear={last['gear']}")
    c.close()


def phase_timeout():
    """Stop answering after one action: bridge must release after timeout_ms."""
    c = client()
    c.configure(sync=True, timeout_ms=300, stream_every=0)
    start = c.reset(episode=2)
    st = c.step(2, 1, start["seq"], Action(0.8, True, False, 5))
    t = time.monotonic()
    rel = c.wait_for(lambda m: m.get("event") == "released", 3)
    SUMMARY["timeout"] = {"reason": rel["reason"], "boundary_tick": st["tick_ms"],
                          "release_tick": rel["tick_ms"],
                          "wall_after_boundary_ms": (rel["_rx_mono"] - t) * 1000}
    c.configure(sync=False, timeout_ms=300, stream_every=5)
    after = c.wait_for(lambda m: m["kind"] == "state" and m.get("reason") == "stream", 3)
    SUMMARY["timeout"]["inputs_after"] = after["inputs"]
    SUMMARY["timeout"]["car_inputs_after"] = after["car_inputs"]
    log(f"timeout: {SUMMARY['timeout']}")
    c.configure(sync=True, timeout_ms=1000, stream_every=0)
    c.close()


def phase_disconnect():
    """Arm a held action, then kill the socket without REL; reconnect and inspect."""
    results = {}
    for mode in ("sync", "async"):
        c = client()
        c.configure(sync=(mode == "sync"), timeout_ms=500, stream_every=0)
        start = c.reset(episode=3 if mode == "sync" else 4)
        c.step(start["episode"], 1, start["seq"], Action(1.0, True, False, 25))
        c.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")
        c.sock.close(); c.sock = None   # abrupt close, no REL sent
        time.sleep(1.0)
        c2 = BridgeClient(trace=TRACE); c2.connect()
        c2.configure(sync=False, timeout_ms=500, stream_every=5)
        after = c2.wait_for(lambda m: m["kind"] == "state" and m.get("reason") == "stream", 3)
        results[mode] = {"inputs_after": after["inputs"], "car_inputs_after": after["car_inputs"],
                         "armed_after": after["armed"]}
        c2.configure(sync=True, timeout_ms=1000, stream_every=0)
        c2.close()
    SUMMARY["disconnect"] = results
    log(f"disconnect: {results}")


def phase_async():
    """Real-time mode: game never waits; measure stale/late actions."""
    c = client()
    c.configure(sync=False, timeout_ms=200, stream_every=0)
    start = c.reset(episode=5)
    prev, rows = start, []
    for aid in range(1, 61):
        st = c.step(5, aid, prev["seq"], Action(0.0, True, False, 5))
        rows.append({"tick_gap": st["tick_ms"] - prev["tick_ms"],
                     "latency_ms": st["_latency_s"] * 1000,
                     "applied_minus_prev": st["applied_tick_ms"] - prev["tick_ms"]})
        prev = st
    c.send_line("REL")
    c.configure(sync=True, timeout_ms=1000, stream_every=0)
    gaps = [r["tick_gap"] for r in rows]
    late = [r["applied_minus_prev"] for r in rows]
    SUMMARY["async"] = {"steps": len(rows), "tick_gap_counts": {g: gaps.count(g) for g in set(gaps)},
                        "apply_delay_ticks_ms": {d: late.count(d) for d in set(late)},
                        "latency_ms_median": statistics.median(r["latency_ms"] for r in rows)}
    log(f"async: {SUMMARY['async']}")
    c.close()


def phase_stream():
    """Passive: record states/events while a human drives (checkpoints, finish)."""
    seconds = float(sys.argv[sys.argv.index("--seconds") + 1]) if "--seconds" in sys.argv else 90
    c = client()
    c.configure(sync=False, timeout_ms=1000, stream_every=10)
    log(f"stream: recording {seconds:.0f}s — drive the race now")
    msgs = c.drain(seconds)
    ev = [m for m in msgs if m["kind"] == "event"]
    SUMMARY["stream"] = {"messages": len(msgs),
                         "events": [{k: m.get(k) for k in ("event", "current", "target", "finished",
                                                             "race_time_ms", "race_ms", "new_state")}
                                    for m in ev]}
    log(json.dumps(SUMMARY["stream"], indent=1))
    c.configure(sync=True, timeout_ms=1000, stream_every=0)
    c.close()


def phase_midhold():
    """Abrupt disconnect in the middle of a 25-tick hold (async mode, no REL)."""
    c = client()
    c.configure(sync=False, timeout_ms=200, stream_every=0)
    start = c.reset(episode=6)
    c.send_line(Action(1.0, True, False, 25).encode(episode=6, action_id=1,
                                                    source_seq=start["seq"]).decode().strip())
    time.sleep(0.05)
    c.sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, b"\x01\x00\x00\x00\x00\x00\x00\x00")
    c.sock.close(); c.sock = None
    c2 = BridgeClient(trace=TRACE); c2.connect()
    c2.configure(sync=False, timeout_ms=200, stream_every=1)
    states = [c2.wait_for(lambda m: m["kind"] == "state" and m.get("reason") == "stream", 3)
              for _ in range(60)]
    first_zero = next((s for s in states if s["inputs"] == [0, 0, 0]), None)
    SUMMARY["midhold"] = {"applied_tick": states[0]["applied_tick_ms"],
                          "first_state_tick": states[0]["tick_ms"],
                          "first_state_inputs": states[0]["inputs"],
                          "first_released_tick": first_zero and first_zero["tick_ms"],
                          "released_all_after": all(s["inputs"] == [0, 0, 0]
                                                    for s in states[states.index(first_zero):])
                          if first_zero else False}
    log(f"midhold: {SUMMARY['midhold']}")
    c2.configure(sync=True, timeout_ms=1000, stream_every=0)
    c2.close()


PHASES = {"hello": phase_hello, "ping": phase_ping, "control": phase_control,
          "timeout": phase_timeout, "disconnect": phase_disconnect, "async": phase_async,
          "stream": phase_stream, "midhold": phase_midhold}

if __name__ == "__main__":
    wanted = [a for a in sys.argv[1:] if a in PHASES] or ["hello", "ping", "control"]
    try:
        for name in wanted:
            log(f"== {name}")
            PHASES[name]()
    except BridgeError as exc:
        SUMMARY["error"] = str(exc)
        log(f"BRIDGE ERROR: {exc}")
    finally:
        (OUT / "summary.json").write_text(json.dumps(SUMMARY, indent=1, default=str))
        log(f"artifacts: {OUT}")
