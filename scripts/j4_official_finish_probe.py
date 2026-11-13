"""J4 probe: does bridge >= 0.4.0 official_finish let TMNF commit a controlled finish?

Drives ONE race of A01 with the SCRIPTED, NOT LEARNED controller reference_pursuit_v1, real
time, speed 1, from the normal start, in official_finish mode (no PreventSimulationFinish, no
auto restart). Records: the finish state, whether the normal end-of-race dialog opens
(game_state 1024), and any new or modified file in the game's replay Autosaves folder.
A new autosave is evidence that the game recorded the run; its content is not parsed here.
After the dialog the game cannot be reset by the plugin: the user restarts the race manually.

Usage: uv run python scripts/j4_official_finish_probe.py --map configs/maps/a01.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trackmania_rl import reward as rw  # noqa: E402
from trackmania_rl import scripted_controllers as sc  # noqa: E402
from trackmania_rl.bridge import BridgeClient, BridgeError, jsonl_tracer  # noqa: E402
from trackmania_rl.runtime import build_env, load_map_assets  # noqa: E402

AUTOSAVES = (pathlib.Path.home() / ".local/share/Steam/steamapps/compatdata/11020/pfx/drive_c"
             "/users/steamuser/Documents/TrackMania/Tracks/Replays/Autosaves")


def snapshot(folder: pathlib.Path) -> dict:
    if not folder.is_dir():
        return {}
    return {p.name: {"mtime": p.stat().st_mtime, "size": p.stat().st_size,
                     "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
            for p in folder.iterdir() if p.is_file()}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    ap.add_argument("--episode", type=int, default=990001)
    ap.add_argument("--dialog-wait-s", type=float, default=8.0)
    a = ap.parse_args()
    assets = load_map_assets(a.map)
    out = ROOT / "runs" / "j4" / f"{time.strftime('%Y%m%d-%H%M%S')}-official-finish-probe"
    out.mkdir(parents=True)
    trace = jsonl_tracer(out / "trace.jsonl")
    bridge = BridgeClient(trace=trace)
    hello = bridge.connect()
    summary = {"controller": "reference_pursuit_v1", "controller_learned": False,
               "data_kind": "real_scripted_test", "learning_data": False,
               "mode": "realtime", "speed": 1.0, "hello": {k: v for k, v in hello.items()
                                                            if not k.startswith("_")}}
    if hello.get("map_uid") != assets["profile"]["uid"] or hello.get("game_state") != 512:
        summary["refused"] = "A01 not in race; nothing sent"
        (out / "summary.json").write_text(json.dumps(summary, indent=1))
        bridge.close(release=False)
        print(json.dumps(summary, indent=1))
        return 2
    before = snapshot(AUTOSAVES)
    env = build_env(bridge, assets, first_episode=a.episode)
    env.realtime_max_lag_ms = 50
    try:
        summary["config_event"] = {k: v for k, v in env.configure(
            1000, auto_restart=False, sync=False, official_finish=True).items()
            if not k.startswith("_")}
        bridge.set_speed(1.0)
        ctl = sc.ReferencePursuit(assets["line"])
        env.reset()
        t, steps, invalid = None, 0, 0
        while steps < 1500:
            t = env.step(ctl.act(env))
            steps += 1
            invalid += not t.valid
            if t.done:
                break
        summary.update({"status": t.status if t else None, "race_ms": t.race_ms if t else None,
                        "transitions": steps, "invalid": invalid,
                        "checkpoints": env.last_state.get("checkpoints") if env.last_state else None})
        events = []
        dialog = None
        if t and t.status == rw.FINISHED:
            try:
                dialog = bridge.wait_for(lambda m: m.get("event") == "game_state"
                                         and m.get("new_state") == 1024, a.dialog_wait_s)
            except BridgeError:
                dialog = None
        events = [{k: v for k, v in m.items() if not k.startswith("_")} for m in list(bridge.pending)
                  if m.get("kind") == "event" and m.get("event") in
                  ("finish", "finish_unprevented", "finish_prevented", "checkpoint", "released")]
        summary["finish_events"] = events
        summary["normal_end_dialog"] = dialog is not None
        time.sleep(3.0)   # let the game write its autosave replay
    finally:
        try:
            bridge.send_line("REL")
            bridge.configure(sync=True, timeout_ms=1000, stream_every=0)
        except (BridgeError, OSError):
            pass
        bridge.close()
        trace.close()
    after = snapshot(AUTOSAVES)
    summary["autosaves_new_or_changed"] = {k: v for k, v in after.items() if before.get(k) != v}
    summary["autosaves_folder"] = str(AUTOSAVES)
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    print(f"artifacts: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
