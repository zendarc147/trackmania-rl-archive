"""Read-only hybrid SAC probes. Local RNGs never perturb async collection/training.

A fixed uniform sample and separate terminal samples are retained in model.zip.
Empty terminal groups may be populated later; a populated group stays fixed.
These are replay diagnostics, not independent estimates of driving performance.
"""
from __future__ import annotations

import contextlib
import hashlib

import numpy as np
import torch
import torch.nn.functional as F


def capture_probe(model, *, size=2048, terminal_size=64, seed=123, existing=None):
    rb = model.replay_buffer
    probe = dict(existing or {})
    reward_cfg = model._critic_reward_config
    bonus = reward_cfg["finish_bonus"]
    separate = bonus > 2 * reward_cfg["time_cost_per_s"] * model._critic_step_s
    expected = {"uniform", "finish", "abandon"} if separate else {"uniform", "terminal"}
    if expected.issubset(probe):
        return probe
    with (rb._lk() if hasattr(rb, "_lk") else contextlib.nullcontext()):
        n = rb.size()
        if not n:
            return probe
        # Use only valid slots; no zero-filled capacity and no optimized-memory alias.
        if rb.optimize_memory_usage or rb.n_envs != 1:
            raise ValueError("critic probes require non-optimized single-environment replay")
        rng = np.random.default_rng(seed)
        indices = np.arange(n)
        terminal = (rb.dones[:n, 0] != 0) & (rb.timeouts[:n, 0] == 0)
        # The residual separates finish bonus from delta/potential and time terms.
        # A finish shorter than one action differs by <= one action's time cost.
        base = (-reward_cfg["progress_scale"] * rb.observations[:n, 0, 16]
                if reward_cfg.get("progress_mode", "potential") == "potential" else
                reward_cfg["progress_scale"] * (rb.next_observations[:n, 0, 16] - rb.observations[:n, 0, 16]))
        base = base - reward_cfg["time_cost_per_s"] * model._critic_step_s
        if separate:
            finish = terminal & (rb.rewards[:n, 0] - base > bonus / 2)
            groups = {"uniform": indices, "finish": indices[finish], "abandon": indices[terminal & ~finish]}
        else:
            groups = {"uniform": indices, "terminal": indices[terminal]}
        for name, choices in groups.items():
            if name in probe or not len(choices):
                continue
            limit = size if name == "uniform" else terminal_size
            ix = choices if limit == 0 or len(choices) <= limit else rng.choice(choices, limit, replace=False)
            data = {key: getattr(rb, key)[ix, 0].copy() for key in
                    ("observations", "next_observations", "actions", "rewards", "dones", "timeouts")}
            data["id"] = hashlib.sha256(b"".join(data[k].tobytes() for k in sorted(data))).hexdigest()
            probe[name] = data
    return probe


def evaluate_probe(model, probe, *, seed=987, batch_size=512):
    """Exact terminal targets; fixed Gaussian noise for nonterminal soft targets."""
    result = {}
    with torch.no_grad():
        alpha = (model.log_ent_coef.exp() if model.log_ent_coef is not None else
                 model.ent_coef_tensor * torch.ones(2, device=model.device))
        for name, group in probe.items():
            generator = torch.Generator(device=model.device).manual_seed(seed)
            values = []
            for start in range(0, len(group["rewards"]), batch_size):
                d = {key: torch.as_tensor(val[start:start + batch_size], device=model.device)
                     for key, val in group.items() if key != "id"}
                mean, log_std, logits = model.actor.distributions(d["next_observations"])
                std = log_std.exp()
                noise = torch.randn(mean.shape, generator=generator, device=model.device)
                gaussian = mean + std * noise
                steer = gaussian.tanh()
                log_steer = (torch.distributions.Normal(mean, std).log_prob(gaussian).sum(1)
                             - torch.log(1 - steer.square() + 1e-6).sum(1))
                log_p = F.log_softmax(logits, dim=-1)
                q_next = model._expected_q(model.critic_target, d["next_observations"], steer)
                v = (log_p.exp() * (q_next - alpha[1] * log_p)).sum(1) - alpha[0] * log_steer
                done = d["dones"] * (1 - d["timeouts"])
                y = d["rewards"] + (1 - done) * model.gamma * v
                q = torch.cat(model.critic(d["observations"], d["actions"]), dim=1)
                errors = q - y[:, None]
                values.append(torch.stack((errors.square().mean(1), errors.abs().amax(1),
                                           q.abs().amax(1)), dim=1).cpu().numpy())
            a = np.concatenate(values)
            result[name] = {"id": group["id"], "count": len(a), "mse": float(a[:, 0].mean()),
                            "td_abs_p95": float(np.quantile(a[:, 1], .95)),
                            "td_abs_max": float(a[:, 1].max()), "q_abs_max": float(a[:, 2].max())}
    return result


def log_fixed_probe(model):
    model._critic_probe = capture_probe(model, size=model._critic_probe_size,
                                       existing=getattr(model, "_critic_probe", None))
    for name, metrics in evaluate_probe(model, model._critic_probe).items():
        for key, value in metrics.items():
            if key != "id":
                model.logger.record(f"diagnostics/fixed_{name}_{key}", value)


def audit_checkpoint(path, *, samples=10000, seed=123):
    """Offline audit of saved data, including EVERY terminal record separately."""
    from .evaluation import load_policy
    model, state = load_policy(path)
    if not hasattr(model.actor, "distributions"):
        raise ValueError("audit-critic currently supports hybrid SAC checkpoints")
    model.load_replay_buffer(path / "replay_buffer.pkl")
    model._critic_reward_config = state["config"].get("reward", {})
    from .reward import RewardConfig
    model._critic_reward_config = RewardConfig(**model._critic_reward_config).__dict__
    model._critic_step_s = state["derived"]["step_s"]
    probe = capture_probe(model, size=samples, terminal_size=0, seed=seed)
    result = {"checkpoint": str(path), "seed": seed, "replay_size": model.replay_buffer.size(),
              "normalization_sha256": state["observation_normalization_sha256"],
              "observation_schema": state["config"].get("observation_schema", "trackmania_rl.observation/1"),
              "groups": evaluate_probe(model, probe),
              "note": "Replay audit, not a driving evaluation. Uniform is sampled; terminal groups are exhaustive. "
                      "Terminal types inferred from reward formula; without a distinguishable finish bonus, grouped as terminal."}
    if getattr(model, "_critic_probe", None):
        result["fixed_training_probe"] = evaluate_probe(model, model._critic_probe)
    return result
