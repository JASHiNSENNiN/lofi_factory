"""
bandit.py — Beta-Bernoulli Thompson Sampling multi-armed bandit.

A small, dependency-free (stdlib `random` only) reusable bandit used across
the analytics feedback loop to pick among pillars, duration buckets, title
variants, and thumbnail variants based on binarized performance (see
`composite_engagement_score()` / `_bandit_weights()` in scripts/analytics.py
for how "success"/"failure" is derived from the composite engagement KPI).

Algorithm
---------
Each arm keeps a Beta(alpha, beta) posterior over its true (binarized)
success probability, starting from the uninformative Jeffreys-ish prior
Beta(1, 1) (uniform on [0, 1]):

    alpha_i = 1 + successes_i
    beta_i  = 1 + failures_i

To *select* an arm, Thompson Sampling draws one sample theta_i ~ Beta(alpha_i,
beta_i) per arm and picks the argmax (`select_arm`). This naturally balances
exploration (arms with wide/uncertain posteriors occasionally win by chance)
and exploitation (arms with a track record of success win more often as
their posterior concentrates) without any hand-tuned epsilon or decay
schedule.

`sample_all()` exposes the same per-arm draws as a plain dict so callers that
already do their own `random.choices(weights=...)` (generate_seo.py,
run.py) can keep their existing call sites; `posterior_mean()` /
`posterior_stats()` expose the deterministic posterior (no sampling) for
dashboards and tests that need a reproducible number instead of a fresh draw.

Reference (studied for algorithm structure/API shape only -- nothing copied,
see repo license-discipline notes in the task writeup): st-tech/zr-obp
(Apache-2.0) and alison-carrera/mabalgs (Apache-2.0) both implement
Beta-Bernoulli Thompson Sampling bandits. This is a from-scratch
implementation using only `random.betavariate` from the Python standard
library.
"""
from __future__ import annotations

import random as _random_mod


class ThompsonSamplingBandit:
    """Beta-Bernoulli Thompson Sampling bandit over a fixed (or growing) set
    of named arms.

    Args:
        arms: initial arm names (str or any hashable). More arms can be
              added implicitly by calling update()/update_counts() with a
              new name -- it starts from the Beta(1,1) prior.
        seed: optional int seed for a private, deterministic random.Random
              instance (use this in tests for reproducible sampling).
        rng:  optional pre-built random.Random (or any object exposing
              .betavariate(a, b)) -- takes precedence over `seed`.
    """

    def __init__(self, arms=(), seed: int | None = None, rng=None):
        self.arms: list = list(arms)
        self.alpha: dict = {a: 1.0 for a in self.arms}
        self.beta: dict = {a: 1.0 for a in self.arms}
        self.n: dict = {a: 0 for a in self.arms}
        if rng is not None:
            self._rng = rng
        elif seed is not None:
            self._rng = _random_mod.Random(seed)
        else:
            self._rng = _random_mod

    def _ensure_arm(self, arm) -> None:
        if arm not in self.alpha:
            self.arms.append(arm)
            self.alpha[arm] = 1.0
            self.beta[arm] = 1.0
            self.n[arm] = 0

    def update(self, arm, success: bool) -> None:
        """Record a single Bernoulli outcome for `arm`."""
        self._ensure_arm(arm)
        if success:
            self.alpha[arm] += 1.0
        else:
            self.beta[arm] += 1.0
        self.n[arm] += 1

    def update_counts(self, arm, successes: float, failures: float) -> None:
        """Record a batch of outcomes for `arm` at once (equivalent to
        calling update() `successes` times with True and `failures` times
        with False, but O(1))."""
        self._ensure_arm(arm)
        self.alpha[arm] += successes
        self.beta[arm] += failures
        self.n[arm] += successes + failures

    def sample(self, arm) -> float:
        """Draw one sample from arm's Beta(alpha, beta) posterior."""
        a = self.alpha.get(arm, 1.0)
        b = self.beta.get(arm, 1.0)
        return self._rng.betavariate(a, b)

    def sample_all(self) -> dict:
        """{arm: one posterior draw} for every known arm."""
        return {a: self.sample(a) for a in self.arms}

    def select_arm(self):
        """Thompson Sampling arm selection: sample every arm once, return the
        argmax. Raises ValueError if the bandit has no arms."""
        if not self.arms:
            raise ValueError("bandit has no arms to select from")
        samples = self.sample_all()
        return max(samples, key=samples.get)

    def posterior_mean(self, arm) -> float:
        """Deterministic posterior mean E[theta_i] = alpha / (alpha + beta)
        (no sampling -- useful for dashboards/tests that want a stable
        number rather than a fresh stochastic draw)."""
        a = self.alpha.get(arm, 1.0)
        b = self.beta.get(arm, 1.0)
        return a / (a + b)

    def posterior_stats(self) -> dict:
        """{arm: {alpha, beta, n, mean}} for every known arm -- feeds the
        dashboard's bandit-posterior panel."""
        return {
            a: {
                "alpha": self.alpha[a],
                "beta": self.beta[a],
                "n": self.n[a],
                "mean": self.posterior_mean(a),
            }
            for a in self.arms
        }
