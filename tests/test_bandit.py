import random

import pytest

from scripts.bandit import ThompsonSamplingBandit


def test_new_bandit_starts_at_uniform_prior():
    b = ThompsonSamplingBandit(["a", "b"])
    assert b.alpha == {"a": 1.0, "b": 1.0}
    assert b.beta == {"a": 1.0, "b": 1.0}
    assert b.posterior_mean("a") == pytest.approx(0.5)
    assert b.posterior_mean("b") == pytest.approx(0.5)


def test_update_single_outcome_moves_posterior():
    b = ThompsonSamplingBandit(["a"])
    b.update("a", True)
    assert b.alpha["a"] == pytest.approx(2.0)
    assert b.beta["a"] == pytest.approx(1.0)
    assert b.n["a"] == 1
    b.update("a", False)
    assert b.alpha["a"] == pytest.approx(2.0)
    assert b.beta["a"] == pytest.approx(2.0)
    assert b.n["a"] == 2


def test_update_counts_batch_matches_individual_updates():
    batch = ThompsonSamplingBandit(["a"])
    batch.update_counts("a", successes=7, failures=3)

    individual = ThompsonSamplingBandit(["a"])
    for _ in range(7):
        individual.update("a", True)
    for _ in range(3):
        individual.update("a", False)

    assert batch.alpha["a"] == pytest.approx(individual.alpha["a"])
    assert batch.beta["a"] == pytest.approx(individual.beta["a"])
    assert batch.n["a"] == individual.n["a"] == 10


def test_posterior_mean_reflects_observed_rate_with_prior_smoothing():
    b = ThompsonSamplingBandit(["a"])
    b.update_counts("a", successes=99, failures=1)
    # Bayesian shrinkage toward the Beta(1,1) prior: (1+99)/(2+100) not 0.99 exactly
    assert b.posterior_mean("a") == pytest.approx(100 / 102)


def test_new_arm_seen_only_via_update_starts_from_prior():
    b = ThompsonSamplingBandit(["a"])
    b.update("brand_new_arm", True)
    assert "brand_new_arm" in b.arms
    assert b.alpha["brand_new_arm"] == pytest.approx(2.0)
    assert b.beta["brand_new_arm"] == pytest.approx(1.0)


def test_sample_is_deterministic_given_seeded_rng():
    b1 = ThompsonSamplingBandit(["a", "b"], seed=42)
    b2 = ThompsonSamplingBandit(["a", "b"], seed=42)
    b1.update_counts("a", 5, 2)
    b1.update_counts("b", 1, 6)
    b2.update_counts("a", 5, 2)
    b2.update_counts("b", 1, 6)
    assert b1.sample_all() == b2.sample_all()


def test_sample_with_explicit_rng_instance_is_reproducible():
    rng1 = random.Random(7)
    rng2 = random.Random(7)
    b1 = ThompsonSamplingBandit(["a", "b"], rng=rng1)
    b2 = ThompsonSamplingBandit(["a", "b"], rng=rng2)
    for _ in range(20):
        assert b1.sample("a") == b2.sample("a")
        assert b1.sample("b") == b2.sample("b")


def test_posterior_stats_shape():
    b = ThompsonSamplingBandit(["a", "b"])
    b.update_counts("a", 3, 1)
    stats = b.posterior_stats()
    assert set(stats.keys()) == {"a", "b"}
    assert stats["a"]["alpha"] == pytest.approx(4.0)
    assert stats["a"]["beta"] == pytest.approx(2.0)
    assert stats["a"]["n"] == 4
    assert stats["a"]["mean"] == pytest.approx(4.0 / 6.0)
    assert stats["b"]["n"] == 0
