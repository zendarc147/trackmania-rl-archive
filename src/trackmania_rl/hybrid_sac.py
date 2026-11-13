"""SAC with a Gaussian steering head and a four-way categorical gas/brake head.

Unlike a continuous score/argmax codec, the categorical distribution is optimized
with an exact expectation over all four commands. Replay contains the command's
one-hot encoding; only steering is reparameterized. Uses SB3's collection,
checkpoint and replay machinery. No additional dependency beyond PyTorch/SB3.

Two critic parameterizations of the same function Q(s, steer, command):
  action_input  (HybridSAC, J4 original) twin MLPs on [s, steer, one-hot]; the expectation
                over the four commands costs four critic passes on a 4x batch.
  q4            (HybridQ4SAC, config sac.hybrid_critic = "q4") twin MLPs on [s, steer] with
                four outputs, one per command in actions.COMBOS order; the expectation
                costs one pass. Proposition J4-04, not validated by any learning result.
"""
from __future__ import annotations

import numpy as np
import torch as th
import torch.nn as nn
import torch.nn.functional as F
from stable_baselines3 import SAC
from stable_baselines3.common.policies import ContinuousCritic
from stable_baselines3.common.torch_layers import create_mlp
from stable_baselines3.common.utils import polyak_update
from stable_baselines3.sac.policies import Actor, SACPolicy
from stable_baselines3.common.distributions import SquashedDiagGaussianDistribution

from .training import make_filtered_sac_class


class HybridActor(Actor):
    def __init__(self, *args, **kwargs):
        if kwargs.get("use_sde", False):
            raise ValueError("hybrid actor does not support gSDE")
        super().__init__(*args, **kwargs)
        width = self.net_arch[-1] if self.net_arch else self.features_dim
        self.mu = nn.Linear(width, 1)
        self.log_std = nn.Linear(width, 1)
        self.action_dist = SquashedDiagGaussianDistribution(1)
        self.logits = nn.Linear(width, 4)

    def distributions(self, obs):
        latent = self.latent_pi(self.extract_features(obs, self.features_extractor))
        mean = self.mu(latent)
        log_std = th.clamp(self.log_std(latent), -20, 2)
        categorical_logits = self.logits(latent)
        return mean, log_std, categorical_logits

    def sample_heads(self, obs, deterministic=False):
        mean, log_std, logits = self.distributions(obs)
        if deterministic:
            self.action_dist.proba_distribution(mean, log_std)
            steer = self.action_dist.get_actions(deterministic=True)
            log_steer = self.action_dist.log_prob(steer)      # unused by callers
        else:
            # log-density from the Gaussian sample itself (as SB3's Actor does). Inverting the
            # squashed steer instead clamps atanh near +-1: a saturated mean then gets a huge
            # negative log-prob, i.e. a fake huge entropy that the actor loss rewards, and the
            # mean runs away (J4-07 test run, 2026-09-30: full lock, critic loss inf).
            steer, log_steer = self.action_dist.log_prob_from_params(mean, log_std)
        log_probs = F.log_softmax(logits, dim=-1)
        probabilities = log_probs.exp()
        if deterministic:
            index = logits.argmax(dim=-1)
        else:
            index = th.distributions.Categorical(logits=logits).sample()
        return steer, log_steer, probabilities, log_probs, index

    @staticmethod
    def combine(steer, index):
        return th.cat((steer, F.one_hot(index, 4).to(steer.dtype) * 2 - 1), dim=-1)

    def forward(self, obs, deterministic=False):
        steer, _, _, _, index = self.sample_heads(obs, deterministic)
        return self.combine(steer, index)


class HybridPolicy(SACPolicy):
    def make_actor(self, features_extractor=None):
        kwargs = self._update_features_extractor(self.actor_kwargs, features_extractor)
        return HybridActor(**kwargs).to(self.device)


# J4-07: one temperature per head. The J4-02 single target (1 + 1/2 ln 4 = 1.69 nats, ~81 % of
# the reachable ln 2 + ln 4) kept the policy near uniform and drove alpha up to ~13 (night run of
# 2026-09-30). Defaults: steer -1 nat (SB3's -dim convention), command 0.3 ln 4 (~90 % on one).
DEFAULT_TARGET_ENTROPY = (-1.0, float(0.3 * np.log(4)))


class HybridSAC(make_filtered_sac_class()):
    """Exact categorical expectation in Bellman target and actor loss.

    Entropy: log_ent_coef holds two temperatures [steer, command], each tuned towards its own
    target (`hybrid_target_entropy`, nats). A fixed ent_coef applies to both heads.
    """

    def __init__(self, *args, hybrid_target_entropy=DEFAULT_TARGET_ENTROPY, **kwargs):
        self.hybrid_target_entropy = [float(x) for x in hybrid_target_entropy]
        if len(self.hybrid_target_entropy) != 2:
            raise ValueError("hybrid_target_entropy must be [steer, command] in nats")
        # each target must be reachable, else its temperature grows without bound (J4-02)
        if self.hybrid_target_entropy[0] >= np.log(2) or self.hybrid_target_entropy[1] >= np.log(4):
            raise ValueError("targets must stay below the uniform entropies: steer ln 2, command ln 4")
        super().__init__(*args, **kwargs)

    def _setup_model(self):
        super()._setup_model()
        if self.ent_coef_optimizer is not None:
            init = float(self.log_ent_coef.detach().exp()[0])
            self.log_ent_coef = th.log(th.full((2,), init, device=self.device)).requires_grad_(True)
            self.ent_coef_optimizer = th.optim.Adam([self.log_ent_coef], lr=self.lr_schedule(1))

    def _sample_action(self, learning_starts, action_noise=None, n_envs=1):
        if self.num_timesteps < learning_starts and not self._use_loaded_policy:
            steer = np.random.uniform(-1, 1, (n_envs, 1)).astype(np.float32)
            indices = np.random.randint(4, size=n_envs)
            choice = np.eye(4, dtype=np.float32)[indices] * 2 - 1
            action = np.concatenate((steer, choice), axis=1)
            return action, action.copy()
        return super()._sample_action(learning_starts, action_noise, n_envs)

    @staticmethod
    def _choices(steer):
        batch = steer.shape[0]
        indices = th.arange(4, device=steer.device).repeat(batch)
        return HybridActor.combine(steer.repeat_interleave(4, dim=0), indices)

    @staticmethod
    def _expected_q(critic, obs, steer):
        batch = obs.shape[0]
        choices = HybridSAC._choices(steer)
        values = th.cat(critic(obs.repeat_interleave(4, dim=0), choices), dim=1)
        return values.min(dim=1).values.reshape(batch, 4)

    def train(self, gradient_steps: int, batch_size: int = 64) -> None:
        self.policy.set_training_mode(True)
        optimizers = [self.actor.optimizer, self.critic.optimizer]
        if self.ent_coef_optimizer is not None:
            optimizers.append(self.ent_coef_optimizer)
        self._update_learning_rate(optimizers)
        actor_losses, critic_losses, entropy_losses, alphas, head_entropy = [], [], [], [], []
        if self.ent_coef_optimizer is not None and self.log_ent_coef.numel() != 2:
            raise ValueError("checkpoint uses the single J4-02 entropy temperature; it cannot be "
                             "trained with the per-head temperatures of J4-07 (evaluation is fine)")
        targets = th.tensor(self.hybrid_target_entropy, device=self.device)
        for step in range(gradient_steps):
            data = self.replay_buffer.sample(batch_size, env=self._vec_normalize_env)
            discounts = data.discounts if data.discounts is not None else self.gamma
            steer, log_steer, probs, log_probs, _ = self.actor.sample_heads(data.observations)
            logs = th.stack((log_steer, (probs * log_probs).sum(dim=1)), dim=1)   # -entropy per head
            if self.ent_coef_optimizer is not None:
                alpha = self.log_ent_coef.detach().exp()
                entropy_loss = -(self.log_ent_coef * (logs + targets).detach()).mean()
                self.ent_coef_optimizer.zero_grad()
                entropy_loss.backward()
                self.ent_coef_optimizer.step()
                entropy_losses.append(entropy_loss.item())
            else:
                alpha = self.ent_coef_tensor * th.ones(2, device=self.device)
            a_steer, a_cmd = alpha[0], alpha[1]
            alphas.append(alpha.tolist())
            head_entropy.append((-logs.detach().mean(dim=0)).tolist())
            with th.no_grad():
                next_steer, next_log_steer, next_probs, next_logs, _ = self.actor.sample_heads(
                    data.next_observations)
                next_q = self._expected_q(self.critic_target, data.next_observations, next_steer)
                next_value = ((next_probs * (next_q - a_cmd * next_logs)).sum(1, keepdim=True)
                              - a_steer * next_log_steer[:, None])
                target = data.rewards + (1 - data.dones) * discounts * next_value
            current = self.critic(data.observations, data.actions)
            critic_loss = 0.5 * sum(F.mse_loss(q, target) for q in current)
            self.critic.optimizer.zero_grad()
            critic_loss.backward()
            self.critic.optimizer.step()
            critic_losses.append(critic_loss.item())
            # Re-sample the reparameterized steering after the critic update.
            steer, log_steer, probs, log_probs, _ = self.actor.sample_heads(data.observations)
            q = self._expected_q(self.critic, data.observations, steer)
            actor_loss = ((probs * (a_cmd * log_probs - q)).sum(1) + a_steer * log_steer).mean()
            self.actor.optimizer.zero_grad()
            actor_loss.backward()
            self.actor.optimizer.step()
            actor_losses.append(actor_loss.item())
            if not (np.isfinite(critic_losses[-1]) and np.isfinite(actor_losses[-1])):
                # stop the run (async: surfaced to the collector) instead of acting on garbage
                raise FloatingPointError(f"non-finite SAC loss at update {self._n_updates + step}: "
                                         f"critic {critic_losses[-1]}, actor {actor_losses[-1]}")
            if step % self.target_update_interval == 0:
                polyak_update(self.critic.parameters(), self.critic_target.parameters(), self.tau)
                polyak_update(self.batch_norm_stats, self.batch_norm_stats_target, 1.0)
        previous_updates = self._n_updates
        self._n_updates += gradient_steps
        self.logger.record("train/n_updates", self._n_updates, exclude="tensorboard")
        a, h = np.mean(alphas, axis=0), np.mean(head_entropy, axis=0)
        self.logger.record("train/ent_coef_steer", a[0])
        self.logger.record("train/ent_coef_cmd", a[1])
        self.logger.record("train/entropy_steer", h[0])
        self.logger.record("train/entropy_cmd", h[1])
        self.logger.record("train/actor_loss", np.mean(actor_losses))
        self.logger.record("train/critic_loss", np.mean(critic_losses))
        if entropy_losses:
            self.logger.record("train/ent_coef_loss", np.mean(entropy_losses))
        every = getattr(self, "_critic_diagnostics_every", 0)
        if every and previous_updates // every != self._n_updates // every:
            from .critic_diagnostics import log_fixed_probe
            log_fixed_probe(self)


class Q4Critic(ContinuousCritic):
    """Twin critics [s, steer] -> 4 Q-values, one per gas/brake command (COMBOS order).

    forward(obs, actions) keeps the SB3 contract: it returns Q of the command encoded in the
    one-hot part of `actions` (the replayed action), one (batch, 1) tensor per critic.
    all_q(obs, steer) returns the four values per critic, (batch, 4) each, in one pass.
    """

    def __init__(self, observation_space, action_space, net_arch, features_extractor,
                 features_dim, activation_fn=nn.ReLU, normalize_images=True, n_critics=2,
                 share_features_extractor=True):
        super().__init__(observation_space, action_space, net_arch, features_extractor,
                         features_dim, activation_fn, normalize_images, n_critics,
                         share_features_extractor)
        self.q_networks = []
        for idx in range(n_critics):
            q_net = nn.Sequential(*create_mlp(features_dim + 1, 4, net_arch, activation_fn))
            self.add_module(f"qf{idx}", q_net)        # replaces the action-input network
            self.q_networks.append(q_net)

    def all_q(self, obs, steer):
        with th.set_grad_enabled(not self.share_features_extractor):
            features = self.extract_features(obs, self.features_extractor)
        x = th.cat([features, steer], dim=1)
        return tuple(q_net(x) for q_net in self.q_networks)

    def forward(self, obs, actions):
        onehot = (actions[:, 1:] > 0).to(actions.dtype)
        return tuple((q * onehot).sum(dim=1, keepdim=True) for q in self.all_q(obs, actions[:, :1]))

    def q1_forward(self, obs, actions):
        with th.no_grad():
            return self.forward(obs, actions)[0]


class HybridQ4Policy(HybridPolicy):
    def make_critic(self, features_extractor=None):
        kwargs = self._update_features_extractor(self.critic_kwargs, features_extractor)
        return Q4Critic(**kwargs).to(self.device)


class HybridQ4SAC(HybridSAC):
    """Same losses as HybridSAC; the four-command expectation uses one critic pass."""

    @staticmethod
    def _expected_q(critic, obs, steer):
        return th.min(th.stack(critic.all_q(obs, steer)), dim=0).values
