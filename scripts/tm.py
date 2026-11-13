"""tm.py — user commands for J4 training runs (D37). No Hermes needed at run time.

  uv run python scripts/tm.py train    --config configs/training/a01_sac_threshold_v1.json
  uv run python scripts/tm.py status   [--run runs/j4/<run_id>]
  uv run python scripts/tm.py stop     --run runs/j4/<run_id>      (or Ctrl+C in the train terminal)
  uv run python scripts/tm.py resume   --run runs/j4/<run_id>
  uv run python scripts/tm.py resume   --run runs/j4/<run_id> --until-stopped
  uv run python scripts/tm.py eval     --run runs/j4/<run_id> [--episodes 20] [--mode sync|realtime]
  uv run python scripts/tm.py trend    --run runs/j4/<run_id>                (learning or random?)
  uv run python scripts/tm.py dashboard [--logdir runs/j4]         (TensorBoard, http://localhost:6006)
  uv run python scripts/tm.py compare  runs/j4/<run_a> runs/j4/<run_b>   (D25, common budget)

Before train/resume/eval: TMInterface with bridge >= 0.3.0, A01 opened from the menu, hands off
the controls. One controller per game: never run two of these commands against the game.
See docs/GUIDE-J4.md.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import pathlib
import subprocess
import sys
import time
from contextlib import contextmanager

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trackmania_rl.bridge import BridgeClient, BridgeError, jsonl_tracer  # noqa: E402
from trackmania_rl.controller_guard import legacy_controller  # noqa: E402
from trackmania_rl.runtime import build_env, load_map_assets, resolve  # noqa: E402

RUNS = ROOT / "runs" / "j4"
MIN_BRIDGE = (0, 3, 0)
MAX_SPEED = 10.0    # GOAL J4 contract


@contextmanager
def controller_lock(command, args):
    """One game controller across CLI and web UI, including separate processes."""
    RUNS.mkdir(parents=True, exist_ok=True)
    with (RUNS / ".controller.lock").open("a+", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("another train, resume or eval controls the game; stop it first")
        active = legacy_controller(ROOT)
        if active is not None:
            raise SystemExit(f"game already controlled by PID {active['pid']} ({active['command']}); stop it first")
        lock.seek(0)
        lock.truncate()
        json.dump({"pid": os.getpid(), "command": command,
                   "run": getattr(args, "run", None), "run_id": getattr(args, "run_id", None),
                   "started": time.strftime("%Y-%m-%dT%H:%M:%S%z")}, lock)
        lock.flush()
        try:
            yield
        finally:
            lock.seek(0)
            lock.truncate()
            lock.flush()
            fcntl.flock(lock, fcntl.LOCK_UN)


def _ver(s):
    try:
        return tuple(int(x) for x in str(s).split("."))
    except ValueError:
        return (0,)


def game_env_factory(cfg: dict, run_dir: pathlib.Path, *, speed: float, sync: bool = True,
                     trace: bool = False, official_finish: bool = False):
    """Return a factory(first_episode) -> EnvHandle that talks to the real game."""
    from trackmania_rl import reward as rw
    from trackmania_rl.training import EnvHandle

    if not 0 < speed <= MAX_SPEED:
        raise SystemExit(f"speed must be in (0, {MAX_SPEED}]")
    assets = load_map_assets(cfg["map"])
    timeout_ms = int(cfg.get("action_timeout_ms", 1000))
    tracer = jsonl_tracer(run_dir / f"bridge_trace_{int(time.time())}.jsonl") if trace else None

    def connect():
        b = BridgeClient(trace=tracer) if tracer else BridgeClient()
        hello = b.connect()
        if _ver(hello.get("bridge_version")) < MIN_BRIDGE:
            b.close(release=False)
            raise SystemExit(f"bridge {hello.get('bridge_version')} too old, need >= 0.3.0")
        if official_finish and _ver(hello.get("bridge_version")) < (0, 4, 0):
            b.close(release=False)
            raise SystemExit("official finish requires bridge >= 0.4.0")
        if hello.get("map_uid") != assets["profile"]["uid"] or hello.get("game_state") not in (512, 1024):
            b.close(release=False)
            raise SystemExit(f"{assets['profile']['name']} is not loaded in the game "
                             f"(map={hello.get('map_name')!r}, state={hello.get('game_state')}): "
                             "open it from the menu first. Nothing was sent.")
        return b, hello

    def factory(first_episode: int) -> EnvHandle:
        bridge, hello = connect()
        env = build_env(bridge, assets, rw.RewardConfig(**cfg.get("reward", {})),
                        action_ticks=int(cfg.get("action_ticks", 5)), first_episode=first_episode,
                        observation_schema=cfg.get("observation_schema", "trackmania_rl.observation/1"),
                        step_timeout_s=float(cfg.get("step_timeout_s", 2.0)))
        env.realtime_max_lag_ms = int(cfg.get("realtime_max_lag_ms", 50))
        env.configure(timeout_ms, auto_restart=not official_finish, sync=sync,
                      official_finish=official_finish)
        sp = bridge.set_speed(speed)

        def recover():
            try:
                env.bridge.close()
            except (BridgeError, OSError):
                pass
            nb, _ = connect()
            env.bridge = nb
            env.configure(timeout_ms, auto_restart=not official_finish, sync=sync,
                          official_finish=official_finish)
            nb.set_speed(speed)

        def close():
            try:
                env.bridge.send_line("REL")
                env.bridge.set_speed(1.0)
                env.bridge.configure(sync=True, timeout_ms=timeout_ms, stream_every=0)
            except (BridgeError, OSError):
                pass
            env.bridge.close()
            if tracer:
                tracer.close()

        info = {"bridge_hello": {k: v for k, v in hello.items() if not k.startswith("_")},
                "speed": speed, "speed_event": {k: sp.get(k) for k in ("requested", "speed_variable")},
                "sync": sync, "action_timeout_ms": timeout_ms,
                "map_profile": str(cfg["map"]), "map_profile_content": assets["profile"]}
        return EnvHandle(env=env, close=close, recover=recover, info=info)

    return factory


def file_hashes() -> dict:
    import hashlib
    out = {}
    for p in sorted([*(ROOT / "src" / "trackmania_rl").glob("*.py"), ROOT / "plugins" / "TrackmaniaRLBridge.as",
                     ROOT / "scripts" / "tm.py", ROOT / "pyproject.toml", ROOT / "uv.lock"]):
        out[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def cmd_train(args, resume_dir=None):
    from trackmania_rl.training import Trainer, load_config, validate_config
    if resume_dir:
        run_dir = resolve(resume_dir)
        cfg = json.loads((run_dir / "config.json").read_text())["config"]
        if not (run_dir / "checkpoints" / "latest.json").exists():
            raise SystemExit("no checkpoint to resume from")
        if args.until_stopped:
            cfg["budget"]["transitions"] = None
        elif args.budget is not None:
            cfg["budget"]["transitions"] = args.budget
    else:
        cfg = load_config(resolve(args.config))
        if args.until_stopped:
            cfg["budget"]["transitions"] = None
        elif args.budget is not None:
            cfg["budget"]["transitions"] = args.budget
        run_id = args.run_id or f"{time.strftime('%Y%m%d-%H%M%S')}-{cfg['name']}"
        run_dir = RUNS / run_id
        if run_dir.exists():
            raise SystemExit(f"{run_dir} exists; use resume")
        run_dir.mkdir(parents=True)
    validate_config(cfg)
    speed = float(args.speed if args.speed is not None else cfg.get("speed", 1.0))
    factory = game_env_factory(cfg, run_dir, speed=speed, trace=args.trace)
    trainer = Trainer(cfg, run_dir, factory, resume=bool(resume_dir),
                      extra_versions={"file_sha256": file_hashes(),
                                      "command": " ".join(sys.argv)})
    print(f"run: {run_dir}\n  stop: uv run python scripts/tm.py stop --run {run_dir.relative_to(ROOT)}"
          f"  (or Ctrl+C here)\n  dashboard: uv run python scripts/tm.py dashboard", flush=True)
    status = trainer.run()
    print(json.dumps({k: status.get(k) for k in ("phase", "stop_reason", "timesteps", "episodes",
                                                  "finishes", "best_finish_ms", "invalid_transitions",
                                                  "sim_hours", "wall_hours", "latest_checkpoint")},
                     indent=1), flush=True)
    return 0


def cmd_stop(args):
    run_dir = resolve(args.run)
    if not (run_dir / "status.json").exists():
        raise SystemExit(f"{run_dir} is not a run directory")
    phase = json.loads((run_dir / "status.json").read_text()).get("phase")
    if phase != "running":
        raise SystemExit(f"{run_dir.name} is not running (phase {phase}); nothing to stop")
    (run_dir / "STOP").write_text(time.strftime("%Y-%m-%dT%H:%M:%S"))
    print(f"STOP requested for {run_dir}: the run finishes its transition, saves a checkpoint and exits.")
    return 0


def _status_line(run_dir):
    s = json.loads((run_dir / "status.json").read_text())
    best = s.get("best_finish_ms")
    budget = s["budget_transitions"]
    progress = (f"{s['timesteps']:>7}/∞ transitions" if budget is None else
                f"{s['timesteps']:>7}/{budget} transitions ({100 * s['budget_fraction']:.1f} %)")
    return (f"{run_dir.name}: {s['phase']:<15} {progress}, sim {s['sim_hours']:.2f} h, episodes {s['episodes']}, "
            f"finishes {s['finishes']}, best {best / 1000 if best else '-'} s, invalid {s['invalid_transitions']}, "
            f"updated {s['updated']}")


def cmd_status(args):
    if args.run:
        run_dir = resolve(args.run)
        print(json.dumps(json.loads((run_dir / "status.json").read_text()), indent=1))
        ep = run_dir / "episodes.jsonl"
        if ep.exists():
            lines = ep.read_text().splitlines()[-5:]
            print("last episodes:")
            for line in lines:
                e = json.loads(line)
                print(f"  ep {e['episode']}: {e['status']:<10} race {e['race_ms']} ms, "
                      f"progress_max {e['progress_max']:.3f}, return {e['return']}")
        return 0
    runs = sorted(p for p in RUNS.glob("*") if (p / "status.json").exists())
    if not runs:
        print("no run in runs/j4")
    for r in runs:
        print(_status_line(r))
    return 0


def cmd_eval(args):
    from trackmania_rl.evaluation import evaluate, load_policy
    run_dir = resolve(args.run)
    cfg = json.loads((run_dir / "config.json").read_text())["config"]
    if args.checkpoint == "latest":
        ck = run_dir / json.loads((run_dir / "checkpoints" / "latest.json").read_text())["dir"]
    elif args.checkpoint == "best":     # snapshot of the best training finish
        ck = run_dir / json.loads((run_dir / "checkpoints" / "best.json").read_text())["dir"]
    else:
        ck = run_dir / "checkpoints" / args.checkpoint
    model, ts = load_policy(ck)
    out = run_dir / "evals" / f"{time.strftime('%Y%m%d-%H%M%S')}-{ck.name}-{args.mode}-x{args.speed:g}"
    out.mkdir(parents=True)
    factory = game_env_factory(cfg, out, speed=args.speed, sync=args.mode == "sync",
                               trace=args.trace, official_finish=args.official_finish)
    handle = factory(int(args.first_episode))
    try:
        summary = evaluate(handle.env, model, ts, episodes=args.episodes, out_dir=out,
                           mode=args.mode, speed=args.speed, official_finish=args.official_finish)
    finally:
        handle.close()
    summary.update({"checkpoint": str(ck.relative_to(ROOT)), "checkpoint_timesteps": ts["timesteps"],
                    "bridge": handle.info["bridge_hello"].get("bridge_version"),
                    "command": " ".join(sys.argv)})
    (out / "eval_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    print(f"artifacts: {out}")
    return 0


def cmd_compare(args):
    from trackmania_rl.compare import compare_runs
    out = compare_runs([resolve(r) for r in args.runs], last_fraction=args.last_fraction)
    text = json.dumps(out, indent=1)
    print(text)
    if args.out:
        resolve(args.out).write_text(text)
    return 0


def cmd_trend(args):
    from trackmania_rl.compare import trend
    out = trend(resolve(args.run), slices=args.slices)
    print(f"{out['run']}  ({out['note']})")
    print("  episodes        steps  prog_med  prog_best  finish  ret_med  cmd_max  |steer|")
    for r in out["slices"]:
        print(f"  {r['episodes']:<13} {r['timesteps_end'] or 0:>7}  {r['progress_max_median']:8.3f}  "
              f"{r['progress_max_best']:9.3f}  {r['finishes']:6d}  {r['return_median']:7.1f}  "
              f"{r['command_share_max']:7.2f}  {r['steer_abs_mean']:7.2f}")
    print(f"  random driving: cmd_max ~0.25, |steer| ~0.50  ->  verdict: {out['verdict']}")
    return 0


def cmd_dashboard(args):
    logdir = resolve(args.logdir)
    print(f"TensorBoard on http://localhost:{args.port}  (logdir {logdir}); Ctrl+C to quit", flush=True)
    return subprocess.call([sys.executable, "-m", "tensorboard.main", "--logdir", str(logdir),
                            "--port", str(args.port), "--bind_all" if args.bind_all else "--host=127.0.0.1"])


def cmd_audit_critic(args):
    import torch
    from trackmania_rl.critic_diagnostics import audit_checkpoint
    if args.samples < 0:
        raise SystemExit("samples must be >= 0 (0 audits the whole replay)")
    torch.set_num_threads(1)
    run = resolve(args.run)
    checkpoint = (run / json.loads((run / "checkpoints/latest.json").read_text())["dir"]
                  if args.checkpoint == "latest" else run / "checkpoints" / args.checkpoint)
    result = audit_checkpoint(checkpoint, samples=args.samples, seed=args.seed)
    text = json.dumps(result, indent=2, allow_nan=False)
    if args.out:
        with resolve(args.out).open("x", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("train")
    t.add_argument("--config", required=True)
    t.add_argument("--run-id")
    t.add_argument("--speed", type=float, help="override the config's simulation speed (<= 10)")
    tg = t.add_mutually_exclusive_group()
    tg.add_argument("--budget", type=int, help="override budget.transitions (<= cap)")
    tg.add_argument("--until-stopped", action="store_true", help="run until STOP or Ctrl+C")
    t.add_argument("--trace", action="store_true", help="log every bridge message (large)")
    r = sub.add_parser("resume")
    r.add_argument("--run", required=True)
    r.add_argument("--speed", type=float)
    rg = r.add_mutually_exclusive_group()
    rg.add_argument("--budget", type=int, help="new total budget in transitions (<= cap)")
    rg.add_argument("--until-stopped", action="store_true", help="ignore the transition cap; run until STOP or Ctrl+C")
    r.add_argument("--trace", action="store_true")
    s = sub.add_parser("stop")
    s.add_argument("--run", required=True)
    st = sub.add_parser("status")
    st.add_argument("--run")
    e = sub.add_parser("eval")
    e.add_argument("--run", required=True)
    e.add_argument("--checkpoint", default="latest", help="latest, best (best training finish) or a directory under checkpoints/")
    e.add_argument("--episodes", type=int, default=20)
    e.add_argument("--mode", choices=["sync", "realtime"], default="sync")
    e.add_argument("--speed", type=float, default=1.0)
    e.add_argument("--first-episode", type=int, default=900001)
    e.add_argument("--trace", action="store_true")
    e.add_argument("--official-finish", action="store_true",
                   help="let TMNF record a finish; requires bridge 0.4.0 and manual restart after an arrival")
    c = sub.add_parser("compare", help="compare runs on their common transition budget (D25)")
    c.add_argument("runs", nargs="+")
    c.add_argument("--last-fraction", type=float, default=0.2)
    c.add_argument("--out")
    tr = sub.add_parser("trend", help="is a run leaving random driving? (indicative)")
    tr.add_argument("--run", required=True)
    tr.add_argument("--slices", type=int, default=5)
    audit = sub.add_parser("audit-critic", help="offline hybrid critic audit; never connects to the game")
    audit.add_argument("--run", required=True)
    audit.add_argument("--checkpoint", default="latest")
    audit.add_argument("--samples", type=int, default=10000, help="uniform sample size; 0 = whole replay")
    audit.add_argument("--seed", type=int, default=123)
    audit.add_argument("--out", help="new JSON report file (existing files are preserved)")
    d = sub.add_parser("dashboard")
    d.add_argument("--logdir", default="runs/j4")
    d.add_argument("--port", type=int, default=6006)
    d.add_argument("--bind-all", action="store_true")
    args = ap.parse_args()
    if args.cmd in ("train", "resume", "eval"):
        with controller_lock(args.cmd, args):
            if args.cmd == "train":
                return cmd_train(args)
            if args.cmd == "resume":
                return cmd_train(args, resume_dir=args.run)
            return cmd_eval(args)
    return {"stop": cmd_stop, "status": cmd_status, "dashboard": cmd_dashboard,
            "compare": cmd_compare, "trend": cmd_trend, "audit-critic": cmd_audit_critic}[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
