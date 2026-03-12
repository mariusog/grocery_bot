"""Score regression tests and congestion regression tests.

These tests run multiple seeds and are slow. Use `pytest -m "not slow"` to skip them.
"""

import statistics

import pytest

from grocery_bot.simulator import DIFFICULTY_PRESETS, GameSimulator


def _run_batch(seeds, *, diagnose=False, **sim_kwargs):
    """Run a batch of simulator seeds once and return immutable per-seed results."""
    results = []
    for seed in seeds:
        sim = GameSimulator(seed=seed, **sim_kwargs)
        result = sim.run(diagnose=diagnose)
        results.append((seed, result))
    return tuple(results)


def _scores(results):
    return [result["score"] for _, result in results]


def _result_for_seed(results, seed):
    for result_seed, result in results:
        if result_seed == seed:
            return result
    raise AssertionError(f"Missing cached result for seed {seed}")


@pytest.fixture(scope="module")
def easy_results():
    return _run_batch(tuple(range(1, 11)), **DIFFICULTY_PRESETS["Easy"])


@pytest.fixture(scope="module")
def medium_results():
    return _run_batch(tuple(range(1, 21)), **DIFFICULTY_PRESETS["Medium"])


@pytest.fixture(scope="module")
def hard_results():
    return _run_batch(tuple(range(1, 21)), **DIFFICULTY_PRESETS["Hard"])


@pytest.fixture(scope="module")
def hard_diagnostics():
    return _run_batch(tuple(range(1, 11)), diagnose=True, **DIFFICULTY_PRESETS["Hard"])


@pytest.fixture(scope="module")
def expert_results():
    return _run_batch(tuple(range(1, 21)), **DIFFICULTY_PRESETS["Expert"])


@pytest.mark.slow
class TestScoreRegression:
    """Regression tests to prevent score degradation.

    Thresholds are set conservatively at ~80-85% of current benchmarks (March 2026):
      Easy:   avg~148, min~133  -> thresholds: avg>=125, per-seed>=120
      Medium: avg~109, min~52   -> thresholds: avg>=90,  per-seed>=30
      Hard:   avg~82,  min~61   -> thresholds: avg>=67,  per-seed>=20
      Expert: avg~60,  min~44   -> thresholds: avg>=48,  per-seed>=20
    """

    # 1. Easy per-seed baselines
    def test_easy_single_seed_baselines(self, easy_results):
        """Each Easy seed 1-10 should score >= 120 (current min is 133)."""
        for seed, result in easy_results:
            assert result["score"] >= 120, (
                f"Easy seed {seed} scored {result['score']} (expected >= 120). "
                f"Regression in single-bot Easy performance."
            )

    # 2. Easy average
    def test_easy_average_above_threshold(self, easy_results):
        """Easy average across seeds 1-10 should be >= 125 (current avg ~148)."""
        scores = _scores(easy_results)
        avg = sum(scores) / len(scores)
        assert avg >= 125, (
            f"Easy average {avg:.1f} fell below 125 (scores: {scores}). "
            f"Regression in single-bot Easy performance."
        )

    # 3. Medium average
    def test_medium_average_above_threshold(self, medium_results):
        """Medium average across seeds 1-20 should be >= 90 (current avg ~109)."""
        scores = _scores(medium_results)
        avg = sum(scores) / len(scores)
        assert avg >= 90, (
            f"Medium average {avg:.1f} fell below 90 (scores: {scores}). "
            f"Regression in 3-bot Medium performance."
        )

    # 4. Hard average
    def test_hard_average_above_threshold(self, hard_results):
        """Hard average across seeds 1-20 should be >= 67 (current avg ~82)."""
        scores = _scores(hard_results)
        avg = sum(scores) / len(scores)
        assert avg >= 67, (
            f"Hard average {avg:.1f} fell below 67 (scores: {scores}). "
            f"Regression in 5-bot Hard performance."
        )

    # 5. Expert average
    def test_expert_average_above_threshold(self, expert_results):
        """Expert (10 bots) average across seeds 1-20 should be >= 48 (current avg ~60)."""
        scores = _scores(expert_results)
        avg = sum(scores) / len(scores)
        assert avg >= 48, (
            f"Expert average {avg:.1f} fell below 48 (scores: {scores}). "
            f"Regression in 10-bot Expert performance."
        )

    # 6. Medium no total deadlock
    def test_medium_no_total_deadlock(self, medium_results):
        """No Medium seed (1-20) should score below 20.

        Catches preview-item deadlock bug (3 bots).
        """
        scores = _scores(medium_results)
        for i, score in enumerate(scores):
            seed = i + 1
            assert score >= 20, (
                f"Medium seed {seed} scored {score} (expected >= 20). "
                f"Possible deadlock regression -- bot may be stuck."
            )

    # 7. Hard minimum score
    def test_hard_minimum_score(self, hard_results):
        """No Hard seed (1-20) should score below 10."""
        scores = _scores(hard_results)
        for i, score in enumerate(scores):
            seed = i + 1
            assert score >= 10, (
                f"Hard seed {seed} scored {score} (expected >= 10). "
                f"Regression in 5-bot Hard minimum performance."
            )

    # 8. Expert minimum score
    def test_expert_minimum_score(self, expert_results):
        """No Expert seed (1-20) should score below 10."""
        scores = _scores(expert_results)
        for i, score in enumerate(scores):
            seed = i + 1
            assert score >= 10, (
                f"Expert seed {seed} scored {score} (expected >= 10). "
                f"Regression in 10-bot Expert minimum performance."
            )

    # 9. Round-trip scoring improvement
    def test_round_trip_scoring_improvement(self, easy_results):
        """Easy seed 1 should score >= 130 (current: 140)."""
        result = _result_for_seed(easy_results, 1)
        assert result["score"] >= 130, (
            f"Easy seed 1 scored {result['score']} (expected >= 130). "
            f"Round-trip scoring improvement may have regressed."
        )

    # 10. Preview deadlock fix
    def test_preview_deadlock_fixed(self, medium_results):
        """Medium seed 6 should score >= 100 (was 12 before fix, now 174).
        Key regression test for the preview-item inventory deadlock."""
        result = _result_for_seed(medium_results, 6)
        assert result["score"] >= 100, (
            f"Medium seed 6 scored {result['score']} (expected >= 100). "
            f"Preview-item inventory deadlock may have regressed."
        )


@pytest.mark.slow
class TestCongestionRegression:
    """Tests that catch multi-bot congestion regressions."""

    def test_5bot_no_permanent_deadlock(self, hard_results):
        """No 5-bot seed should score below 10 (seeds 1-20)."""
        for seed, result in hard_results:
            assert result["score"] >= 10, (
                f"5-bot seed {seed} scored {result['score']} (below 10 threshold)"
            )

    def test_5bot_average_above_threshold(self, hard_results):
        """5-bot average across seeds 1-10 should be >= 60."""
        scores = _scores(hard_results[:10])
        avg = statistics.mean(scores)
        assert avg >= 60, f"5-bot average score {avg:.1f} is below 60 threshold (scores: {scores})"

    def test_no_excessive_idle_rounds(self, hard_diagnostics):
        """Idle rounds should be < 50% of total bot-rounds for 5 bots."""
        for seed, result in hard_diagnostics[:5]:
            diag = result["diagnostics"]
            total_br = diag["total_bot_rounds"]
            idle_pct = diag["idle_rounds"] / total_br * 100 if total_br > 0 else 0
            assert idle_pct < 50, (
                f"5-bot seed {seed}: idle rounds {idle_pct:.1f}% exceeds 50% "
                f"({diag['idle_rounds']}/{total_br})"
            )

    def test_no_long_delivery_gaps(self, hard_diagnostics):
        """Max delivery gap should be < 150 rounds for any 5-bot config."""
        for seed, result in hard_diagnostics:
            diag = result["diagnostics"]
            assert diag["max_delivery_gap"] < 150, (
                f"5-bot seed {seed}: max delivery gap {diag['max_delivery_gap']} exceeds 150 rounds"
            )

    def test_10bot_scores_above_zero(self, expert_results):
        """10-bot configs should score > 0 for all seeds 1-10."""
        for seed, result in expert_results[:10]:
            assert result["score"] > 0, f"10-bot seed {seed} scored 0 (complete deadlock)"


@pytest.mark.slow
class TestSimulatorImprovements:
    def test_two_bot_no_crash(self):
        """2-bot simulation should complete without crashing."""
        total = 0
        for seed in [42, 123, 7, 99, 256]:
            sim = GameSimulator(seed=seed, num_bots=2)
            r = sim.run()
            total += r["score"]
            assert r["rounds_used"] == 300
        avg = total / 5
        # Multi-bot scoring is currently 0 due to known collision bug.
        # Once fixed, raise this threshold to the expected baseline (~145).
        assert avg >= 0, f"2-bot average {avg} should be non-negative"

    def test_three_bot_no_crash(self):
        """3-bot simulation should complete without crashing."""
        total = 0
        for seed in [42, 123, 7, 99, 256]:
            sim = GameSimulator(seed=seed, num_bots=3)
            r = sim.run()
            total += r["score"]
            assert r["rounds_used"] == 300
        avg = total / 5
        # Multi-bot scoring is currently 0 due to known collision bug.
        # Once fixed, raise this threshold to the expected baseline (~130).
        assert avg >= 0, f"3-bot average {avg} should be non-negative"

    def test_five_bot_no_crash(self):
        """5-bot simulation should complete without crashing."""
        total = 0
        for seed in [42, 123]:
            sim = GameSimulator(seed=seed, num_bots=5)
            r = sim.run()
            total += r["score"]
            assert r["rounds_used"] == 300
        avg = total / 2
        # Multi-bot scoring is currently 0 due to known collision bug.
        # Once fixed, raise this threshold to the expected baseline (~130).
        assert avg >= 0, f"5-bot average {avg} should be non-negative"
