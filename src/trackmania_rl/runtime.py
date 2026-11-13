"""Runtime assembly: map assets + bridge -> TrackmaniaEnv. Generic; map values come from the profile.

Shared by the J4 scripts (throughput, training, evaluation) so that every run builds the
environment the same way and records the same identities (hashes, versions).
"""
from __future__ import annotations

import json
import pathlib

from . import reward as rw
from .env import EpisodeRules, TrackmaniaEnv
from .geometry import ProgressTracker, ReferenceLine
from .observation import Encoder, SCHEMA_VERSION
from .reference import canonical_hash, load_map_profile, load_prepared

ROOT = pathlib.Path(__file__).resolve().parents[2]


def resolve(path) -> pathlib.Path:
    p = pathlib.Path(path)
    return p if p.is_absolute() else ROOT / p


def load_map_assets(map_path) -> dict:
    profile = load_map_profile(resolve(map_path))
    ref = profile["reference"]
    prepared = load_prepared(resolve(ref["prepared"]))
    if prepared["sha256"] != ref["prepared_content_sha256"]:
        raise ValueError("prepared reference hash differs from the map profile")
    norm = json.loads(resolve(ref["normalization"]).read_text(encoding="utf-8"))
    if norm.get("sha256") != ref["normalization_content_sha256"]:
        raise ValueError("normalization hash differs from the map profile")
    return {"profile": profile, "prepared": prepared, "line": ReferenceLine(prepared),
            "norm": norm, "map_path": str(map_path)}


def lap_ghost(assets: dict) -> rw.LapGhost:
    """Reference run timing projected on the prepared line (reward/3). The raw reference
    is checked against the map profile; s is the running maximum of the projection."""
    ref = assets["profile"]["reference"]
    raw = json.loads(resolve(ref["raw"]).read_text(encoding="utf-8"))
    if canonical_hash({k: v for k, v in raw.items() if k != "sha256"}) != ref["raw_content_sha256"]:
        raise ValueError("raw reference hash differs from the map profile")
    tracker = ProgressTracker(assets["line"])
    tracker.reset()
    s_m, t_s = [], []
    for x in raw["samples"]:
        p = tracker.update(x["position"], x["race_ms"], x["checkpoints"])
        if not s_m or p.s_m > s_m[-1]:
            s_m.append(p.s_m)
            t_s.append(x["race_ms"] / 1000.0)
    return rw.LapGhost(s_m, t_s, assets["line"].length, raw["race_time_ms"] / 1000.0)


def build_env(bridge, assets: dict, reward_cfg: rw.RewardConfig | None = None, *,
              action_ticks: int = 5, step_timeout_s: float = 2.0,
              reset_timeout_s: float = 15.0, first_episode: int = 1,
              observation_schema: str = SCHEMA_VERSION,
              **rule_overrides) -> TrackmaniaEnv:
    profile = assets["profile"]
    reward_cfg = reward_cfg or rw.RewardConfig()
    return TrackmaniaEnv(bridge, profile, Encoder(assets["norm"], profile["uid"]),
                         ProgressTracker(assets["line"]), reward_cfg,
                         EpisodeRules.from_profile(profile, **rule_overrides),
                         action_ticks=action_ticks, step_timeout_s=step_timeout_s,
                         reset_timeout_s=reset_timeout_s, first_episode=first_episode,
                         observation_schema=observation_schema,
                         ghost=lap_ghost(assets) if reward_cfg.lap_scale else None)
