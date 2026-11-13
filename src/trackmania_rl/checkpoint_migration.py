"""Explicit, non-destructive v1 -> v2 observation migration (J4-15).

Preserve the actor, both critics, target critics and entropy temperatures. New
input columns start at zero, so outputs are initially independent of the two
new fields. Optimizers and replay start fresh: old replay lacks episode context.
No old model or replay is written by this module.
"""
from __future__ import annotations

import re

import torch


def expand_observation_inputs(source, target, base_dim: int = 25, extra: int = 2,
                              mode: str = "observation_v2") -> dict:
    """v1 -> v2 (defaults) or, J6, v2 -> v3: base_dim=27, extra=18 lookahead columns."""
    if (source.observation_space.shape != (base_dim,)
            or target.observation_space.shape != (base_dim + extra,)):
        raise ValueError(f"observation migration {mode}: unexpected input sizes")
    if type(source.policy) is not type(target.policy):
        raise ValueError("observation migration requires the same policy and critic architecture")
    old, new = source.policy.state_dict(), target.policy.state_dict()
    if old.keys() != new.keys():
        raise ValueError("observation migration: incompatible policy parameters")
    expanded = []
    for name, value in old.items():
        if value.shape == new[name].shape:
            new[name] = value.detach().clone()
        elif (name == "actor.latent_pi.0.weight" or
              re.fullmatch(r"critic(?:_target)?\.qf\d+\.0\.weight", name)):
            if (value.ndim != 2 or new[name].shape != (value.shape[0], value.shape[1] + extra)
                    or value.shape[1] < base_dim):
                raise ValueError(f"observation migration: incompatible input layer {name}")
            weight = torch.zeros_like(new[name])
            weight[:, :base_dim] = value[:, :base_dim]
            # Critic action inputs follow observations; shift them after the new fields.
            weight[:, base_dim + extra:] = value[:, base_dim:]
            new[name] = weight
            expanded.append(name)
        else:
            raise ValueError(f"observation migration: incompatible parameter {name}")
    if not expanded:
        raise ValueError("observation migration: no input layers expanded")
    if (source.log_ent_coef is None) != (target.log_ent_coef is None):
        raise ValueError("observation migration: entropy mode differs")
    if source.log_ent_coef is not None and source.log_ent_coef.shape != target.log_ent_coef.shape:
        raise ValueError("observation migration: entropy heads differ")
    target.policy.load_state_dict(new, strict=True)
    with torch.no_grad():
        if source.log_ent_coef is not None:
            target.log_ent_coef.copy_(source.log_ent_coef)
        else:
            target.ent_coef_tensor.copy_(source.ent_coef_tensor)
    target._n_updates = source._n_updates
    target._use_loaded_policy = source._n_updates > 0
    return {"mode": mode, "expanded_parameters": expanded,
            "weights_preserved": ["actor", "critics", "target critics", "entropy temperatures"],
            "optimizers": "fresh", "replay": "fresh; old transitions lack the new fields"}
