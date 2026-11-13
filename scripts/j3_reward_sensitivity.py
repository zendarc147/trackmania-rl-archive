"""J3 reward sensitivity: recompute returns of the REAL J3 episodes under candidate reward configs.

Offline, no game. Inputs: runs/j3/*-env/transitions.jsonl (data_kind real_scripted_test,
controllers NOT LEARNED). For each candidate config, the progress / duration / status of every
valid transition are replayed through reward.compute; the script reports the discounted return
of each episode, the calibration check against the map rules, and whether the ordering
"faster finish > slower finish > abandon" holds. Evidence for choosing proposed coefficients,
not a learning experiment.

Usage: uv run python scripts/j3_reward_sensitivity.py --map configs/maps/a01.json
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from trackmania_rl import reward as rw  # noqa: E402
from trackmania_rl.env import EpisodeRules  # noqa: E402
from trackmania_rl.reference import load_map_profile  # noqa: E402

CANDIDATES = {
    "v1_proposed": rw.RewardConfig(),
    "bonus_100": rw.RewardConfig(finish_bonus=100.0),
    "discount_0.95": rw.RewardConfig(discount_per_second=0.95),
    "discount_0.99": rw.RewardConfig(discount_per_second=0.99),
    "discount_1.0": rw.RewardConfig(discount_per_second=1.0),
    "progress_scale_10": rw.RewardConfig(progress_scale=10.0),
    "time_cost_0.1": rw.RewardConfig(time_cost_per_s=0.1),
}


def load_episodes():
    eps = {}
    for path in sorted((ROOT / "runs" / "j3").glob("*-env/transitions.jsonl")):
        for line in path.read_text().splitlines():
            t = json.loads(line)
            key = (path.parent.name, t["scenario"], t["episode"])
            eps.setdefault(key, []).append(t)
    return eps


def replay(cfg, ts):
    prev = None
    steps = []
    for t in ts:
        if not t["valid"]:
            return None          # invalid transitions are excluded: no return for the episode
        p = t["info"]["progress"]
        if prev is None:
            # progress before the first action: recover it from the recorded shaping term
            c = t["reward_components"]
            g = rw.RewardConfig().gamma(t["dt_ms"] / 1000)
            phi_next = 0.0 if t["status"] in rw.TERMINAL else 100.0 * p
            prev = (g * phi_next - c["progress"]) / 100.0
        steps.append(rw.compute(cfg, prev, p, t["dt_ms"] / 1000, t["status"]))
        prev = p
    return rw.discounted_return(steps)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True)
    args = ap.parse_args()
    profile = load_map_profile(ROOT / args.map)
    rules = EpisodeRules.from_profile(profile)
    eps = load_episodes()
    keep = {k: v for k, v in eps.items()
            if v[-1]["status"] in (rw.FINISHED, rw.ABANDONED) and all(t["valid"] for t in v)}
    out = {"data_kind": "real_scripted_test", "learning_data": False,
           "episodes": {f"{k[0]}/{k[1]}/{k[2]}": {"status": v[-1]["status"], "race_ms": v[-1]["race_ms"],
                                                   "transitions": len(v)} for k, v in keep.items()},
           "candidates": {}}
    for name, cfg in CANDIDATES.items():
        rets = {f"{k[0]}/{k[1]}/{k[2]}": replay(cfg, v) for k, v in keep.items()}
        fin = sorted(((out["episodes"][k]["race_ms"], r) for k, r in rets.items()
                      if out["episodes"][k]["status"] == rw.FINISHED))
        ab = [r for k, r in rets.items() if out["episodes"][k]["status"] == rw.ABANDONED]
        order_ok = (all(a[1] > b[1] for a, b in zip(fin, fin[1:]))
                    and all(min(r for _, r in fin) > x for x in ab))
        cal = rw.check_calibration(cfg, rules.time_limit_ms / 1000, rules.no_progress_ms / 1000)
        out["candidates"][name] = {"config": cfg.to_dict(), "returns": rets,
                                   "order_faster_finish_slower_finish_abandon": order_ok,
                                   "calibration": cal}
        print(f"{name:18s} order_ok={order_ok!s:5s} calib_ok={cal['ok']!s:5s} "
              f"min_bonus={cal['min_finish_bonus']:.1f} "
              + " ".join(f"{r:.2f}" for r in rets.values()), flush=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = ROOT / "runs" / "j3" / f"{stamp}-reward-sensitivity.json"
    dest.write_text(json.dumps(out, indent=1))
    print(f"episodes: {list(out['episodes'])}\nartifact: {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
