"""Off-game throughput benchmark of the J4 learner options (SYNTHETIC game, real SAC compute).

The game is tests/test_env.SyntheticGame (an invented 1-D car, NOT TrackMania) with an added
sleep per action that emulates the wall time of one real 50 ms step (default 5 ms, i.e. the
x10 measurement of runs/j4/20260929-170056-throughput). The SAC network, batch and threads are
the J4 ones, so the gradient cost is real; the game cost is only emulated. Measures wall
transitions per second after learning_starts, and the realised updates per transition.

Usage:
  uv run python scripts/j4_learner_bench.py [--game-ms 5] [--transitions 1500] [--threads 8]
      [--variants hybrid_legacy hybrid_q4_async_r1 ...] [--out runs/j4/logs/learner-bench.json]
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]

VARIANTS = {
    # name: (action_codec, hybrid_critic, learner section or None = historical J4 loop)
    "threshold_legacy": ("threshold_v1", None, None),
    "threshold_async_r1": ("threshold_v1", None, {"mode": "async", "updates_per_transition": 1}),
    "threshold_async_r05": ("threshold_v1", None, {"mode": "async", "updates_per_transition": 0.5}),
    "hybrid_legacy": ("hybrid4_v1", None, None),
    "hybrid_q4_sync_r1": ("hybrid4_v1", "q4", {"mode": "sync", "updates_per_transition": 1}),
    "hybrid_q4_async_r1": ("hybrid4_v1", "q4", {"mode": "async", "updates_per_transition": 1}),
    "hybrid_q4_async_r05": ("hybrid4_v1", "q4", {"mode": "async", "updates_per_transition": 0.5}),
    "hybrid_q4_async_r025": ("hybrid4_v1", "q4", {"mode": "async", "updates_per_transition": 0.25}),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--game-ms", type=float, default=5.0)
    ap.add_argument("--transitions", type=int, default=1500)
    ap.add_argument("--learning-starts", type=int, default=300)
    ap.add_argument("--threads", type=int, default=8)
    ap.add_argument("--variants", nargs="+", default=list(VARIANTS))
    ap.add_argument("--out")
    a = ap.parse_args()

    from test_training import synthetic_factory
    from trackmania_rl.training import Trainer

    def slow_factory():
        inner = synthetic_factory()

        def factory(first):
            h = inner(first)
            game = h.env.bridge
            orig = game.send_line

            def send_line(line):
                if line.startswith("A "):
                    time.sleep(a.game_ms / 1000)
                return orig(line)
            game.send_line = send_line
            return h
        return factory

    out = {"data": "SYNTHETIC game with emulated step time; real SAC compute",
           "game_ms": a.game_ms, "transitions": a.transitions,
           "learning_starts": a.learning_starts, "threads": a.threads, "results": {}}
    for name in a.variants:
        codec, critic, learner = VARIANTS[name]
        cfg = {"name": f"bench_{name}", "map": "SYNTHETIC", "action_codec": codec, "action_ticks": 5,
               "seed": 1, "torch_threads": a.threads, "log_transitions": True,
               "budget": {"transitions": a.transitions},
               "checkpoint_every_transitions": 10 ** 9,
               "sac": {"net_arch": [256, 256], "learning_starts": a.learning_starts,
                       "batch_size": 256, "buffer_size": 100000}}
        if critic:
            cfg["sac"]["hybrid_critic"] = critic
        if learner:
            cfg["learner"] = learner
        with tempfile.TemporaryDirectory() as tmp:
            tr = Trainer(cfg, pathlib.Path(tmp) / "run", slow_factory(), install_signal_handler=False)
            marks = {}
            real = tr.on_transition

            def on_transition(t, raw):
                real(t, raw)
                n = tr.model.num_timesteps + 1
                if n in (a.learning_starts, a.transitions):
                    marks[n] = time.monotonic()
            tr.on_transition = on_transition
            st = tr.run()
            ts = json.loads((pathlib.Path(tmp) / "run" / json.loads(
                (pathlib.Path(tmp) / "run/checkpoints/latest.json").read_text())["dir"]
                / "trainer_state.json").read_text())
        n_learn = a.transitions - a.learning_starts
        dt = marks[a.transitions] - marks[a.learning_starts]
        res = {"transitions_per_wall_s": n_learn / dt,
               "gradient_updates": ts["gradient_updates"],
               "updates_per_transition": ts["gradient_updates"] / n_learn,
               "learner": st.get("learner")}
        out["results"][name] = res
        print(f"{name:<22} {res['transitions_per_wall_s']:7.1f} trans/s   "
              f"UTD {res['updates_per_transition']:.2f}", flush=True)
    text = json.dumps(out, indent=1)
    if a.out:
        pathlib.Path(a.out).write_text(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
