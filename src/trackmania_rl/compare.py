"""Compare training runs on a common transition budget (D25). Generic, reads run files only.

Reads each run's config.json and episodes.jsonl. Only episodes that ended at or before the
common budget (the smallest run's timesteps) are counted, so a longer run gets no advantage.
The result is diagnostic: with one run per arm and one seed, it is not a controlled
comparison, and training episodes are not a frozen evaluation (D28).
"""
from __future__ import annotations

import json
import pathlib
import statistics

COMPARED_KEYS = ("action_codec", "seed", "action_ticks", "speed", "reward", "sac", "learner", "map")


def _load(run: pathlib.Path) -> tuple[dict, list[dict], int]:
    cfg = json.loads((run / "config.json").read_text())["config"]
    status = json.loads((run / "status.json").read_text())
    path = run / "episodes.jsonl"
    eps = [json.loads(line) for line in path.read_text().splitlines() if line.strip()] if path.exists() else []
    return cfg, eps, int(status.get("timesteps", 0))


def _summary(run, cfg, eps, limit, last_fraction):
    window = [e for e in eps if e.get("timesteps") is not None and e["timesteps"] <= limit]
    tail = [e for e in window if e["timesteps"] > limit * (1 - last_fraction)]
    times = [e["finish_ms"] for e in window if e.get("finish_ms") is not None]
    prog = [e["progress_max"] for e in tail if e.get("progress_max") is not None]
    rets = [e["return"] for e in tail if e.get("return") is not None]
    return {"run": run.name, "action_codec": cfg["action_codec"], "seed": cfg["seed"],
            "episodes": len(window), "finishes": len(times),
            "finish_rate": len(times) / len(window) if window else None,
            "best_finish_ms": min(times) if times else None,
            "median_finish_ms": statistics.median(times) if times else None,
            "tail_episodes": len(tail),
            "tail_progress_max_median": statistics.median(prog) if prog else None,
            "tail_progress_max_best": max(prog) if prog else None,
            "tail_return_median": statistics.median(rets) if rets else None}


def compare_runs(runs, last_fraction: float = 0.2) -> dict:
    if not 0 < last_fraction <= 1:
        raise ValueError("last_fraction must be in (0, 1]")
    loaded = [(pathlib.Path(r), *_load(pathlib.Path(r))) for r in runs]
    limit = min(n for _, _, _, n in loaded)
    ref = loaded[0][1]
    diffs = [k for k in COMPARED_KEYS if any(c.get(k) != ref.get(k) for _, c, _, _ in loaded[1:])]
    seeds = {}
    for _, c, _, _ in loaded:
        seeds.setdefault(c["action_codec"], set()).add(c["seed"])
    blocking_diffs = [k for k in diffs if k != "seed"]
    return {"schema": "trackmania_rl.compare/1", "common_transitions": limit,
            "last_fraction": last_fraction, "differences": diffs,
            "controlled": blocking_diffs == ["action_codec"] and all(len(s) >= 2 for s in seeds.values()),
            "note": "training episodes, stochastic policy; not a D28 evaluation",
            "runs": [_summary(r, c, e, limit, last_fraction) for r, c, e, _ in loaded]}


def trend(run, slices: int = 5) -> dict:
    """Per-slice training trend of one run (live or finished): is it leaving random driving?

    Indicative only (stochastic training episodes, not D28). Uniform random driving gives
    command shares ~0.25 each and |steer| mean ~0.5 (night run of 2026-09-30, J4-07).
    """
    _, eps, _ = _load(pathlib.Path(run))
    eps = [e for e in eps if e.get("progress_max") is not None]
    if len(eps) < slices:
        raise ValueError(f"{len(eps)} episodes: not enough for {slices} slices")
    rows = []
    for i in range(slices):
        part = eps[i * len(eps) // slices:(i + 1) * len(eps) // slices]
        shares = {k: statistics.mean(e["action_share"][k] for e in part) for k in part[0]["action_share"]}
        rows.append({"episodes": f"{part[0]['episode']}-{part[-1]['episode']}",
                     "timesteps_end": part[-1].get("timesteps"),
                     "progress_max_median": statistics.median(e["progress_max"] for e in part),
                     "progress_max_best": max(e["progress_max"] for e in part),
                     "finishes": sum(e.get("finish_ms") is not None for e in part),
                     "return_median": statistics.median(e["return"] for e in part if e.get("return") is not None),
                     "command_share_max": max(shares.values()),
                     "command_shares": shares,
                     "steer_abs_mean": statistics.mean(e["steer_abs_mean"] for e in part)})
    first, last = rows[0], rows[-1]
    progress_up = last["progress_max_median"] >= 1.5 * first["progress_max_median"] + 0.02
    committed = last["command_share_max"] >= 0.4
    verdict = ("signs of learning" if progress_up and committed else
               "no sign of learning: stop and diagnose" if not (progress_up or committed) else
               "mixed: keep watching")
    return {"schema": "trackmania_rl.trend/1", "run": pathlib.Path(run).name, "slices": rows,
            "progress_up": progress_up, "commands_committed": committed, "verdict": verdict,
            "note": "indicative, training episodes with a stochastic policy; not a D28 evaluation"}
