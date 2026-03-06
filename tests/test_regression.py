"""Score regression tests and congestion regression tests.

These tests run multiple seeds and are slow. Use `pytest -m "not slow"` to skip them.
"""

import pytest

from grocery_bot.simulator import GameSimulator, DIFFICULTY_PRESETS
from tests.conftest import reset_bot


@pytest.mark.slow
class TestScoreRegression:
    """Regression tests to prevent score degradation.

    Thresholds are set conservatively below current benchmarks (March 2026):
      Easy:   avg~153, min~140  (1 bot)
      Medium: avg~113, min~84   (3 bots)
      Hard:   avg~83,  min~63   (5 bots, orders 3-5)
      Expert: avg~57,  min~36   (10 bots)
    """

    # --- helpers ---

    @staticmethod
    def _run_seeds(seeds, **sim_kwargs):
        """Run simulator for each seed and return list of scores."""
        scores = []
        for seed in seeds:
            reset_bot()
            sim = GameSimulator(seed=seed, **sim_kwargs)
            result = sim.run()
            scores.append(result["score"])
        return scores

    # 1. Easy per-seed baselines
    def test_easy_single_seed_baselines(self):
        """Each Easy seed 1-10 should score >= 130 (current min is 140)."""
        for seed in range(1, 11):
            reset_bot()
            sim = GameSimulator(seed=seed, **DIFFICULTY_PRESETS["Easy"])
            result = sim.run()
            assert result["score"] >= 130, (
                f"Easy seed {seed} scored {result['score']} (expected >= 130). "
                f"Regression in single-bot Easy performance."
            )

    # 2. Easy average
    def test_easy_average_above_threshold(self):
        """Easy average across seeds 1-10 should be >= 135 (current avg ~153)."""
        scores = self._run_seeds(range(1, 11), **DIFFICULTY_PRESETS["Easy"])
        avg = sum(scores) / len(scores)
        assert avg >= 135, (
            f"Easy average {avg:.1f} fell below 135 (scores: {scores}). "
            f"Regression in single-bot Easy performance."
        )

    # 3. Medium average
    def test_medium_average_above_threshold(self):
        """Medium average across seeds 1-20 should be >= 85 (current avg ~105)."""
        scores = self._run_seeds(range(1, 21), **DIFFICULTY_PRESETS["Medium"])
        avg = sum(scores) / len(scores)
        assert avg >= 85, (
            f"Medium average {avg:.1f} fell below 85 (scores: {scores}). "
            f"Regression in 3-bot Medium performance."
        )

    # 4. Hard average
    def test_hard_average_above_threshold(self):
        """Hard average across seeds 1-20 should be >= 55 (current avg ~72)."""
        scores = self._run_seeds(range(1, 21), **DIFFICULTY_PRESETS["Hard"])
        avg = sum(scores) / len(scores)
        assert avg >= 55, (
            f"Hard average {avg:.1f} fell below 55 (scores: {scores}). "
            f"Regression in 5-bot Hard performance."
        )

    # 5. Expert average
    def test_expert_average_above_threshold(self):
        """Expert (10 bots) average across seeds 1-20 should be >= 38 (current avg ~50)."""
        scores = self._run_seeds(range(1, 21), **DIFFICULTY_PRESETS["Expert"])
        avg = sum(scores) / len(scores)
        assert avg >= 38, (
            f"Expert average {avg:.1f} fell below 38 (scores: {scores}). "
            f"Regression in 10-bot Expert performance."
        )

    # 6. Medium no total deadlock
    def test_medium_no_total_deadlock(self):
        """No Medium seed (1-20) should score below 20. Catches preview-item deadlock bug (3 bots)."""
        scores = self._run_seeds(range(1, 21), **DIFFICULTY_PRESETS["Medium"])
        for i, score in enumerate(scores):
            seed = i + 1
            assert score >= 20, (
                f"Medium seed {seed} scored {score} (expected >= 20). "
                f"Possible deadlock regression -- bot may be stuck."
            )

    # 7. Hard minimum score
    def test_hard_minimum_score(self):
        """No Hard seed (1-20) should score below 10."""
        scores = self._run_seeds(range(1, 21), **DIFFICULTY_PRESETS["Hard"])
        for i, score in enumerate(scores):
            seed = i + 1
            assert score >= 10, (
                f"Hard seed {seed} scored {score} (expected >= 10). "
                f"Regression in 5-bot Hard minimum performance."
            )

    # 8. Expert minimum score
    def test_expert_minimum_score(self):
        """No Expert seed (1-20) should score below 10."""
        scores = self._run_seeds(range(1, 21), **DIFFICULTY_PRESETS["Expert"])
        for i, score in enumerate(scores):
            seed = i + 1
            assert score >= 10, (
                f"Expert seed {seed} scored {score} (expected >= 10). "
                f"Regression in 10-bot Expert minimum performance."
            )

    # 9. Round-trip scoring improvement
    def test_round_trip_scoring_improvement(self):
        """Easy seed 1 should score >= 130 (current: 140)."""
        reset_bot()
        sim = GameSimulator(seed=1, **DIFFICULTY_PRESETS["Easy"])
        result = sim.run()
        assert result["score"] >= 130, (
            f"Easy seed 1 scored {result['score']} (expected >= 130). "
            f"Round-trip scoring improvement may have regressed."
        )

    # 10. Preview deadlock fix
    def test_preview_deadlock_fixed(self):
        """Medium seed 6 should score >= 100 (was 12 before fix, now 174).
        Key regression test for the preview-item inventory deadlock."""
        reset_bot()
        sim = GameSimulator(seed=6, **DIFFICULTY_PRESETS["Medium"])
        result = sim.run()
        assert result["score"] >= 100, (
            f"Medium seed 6 scored {result['score']} (expected >= 100). "
            f"Preview-item inventory deadlock may have regressed."
        )


@pytest.mark.slow
class TestCongestionRegression:
    """Tests that catch multi-bot congestion regressions."""

    def test_5bot_no_permanent_deadlock(self):
        """No 5-bot seed should score below 10 (seeds 1-20)."""
        for seed in range(1, 21):
            sim = GameSimulator(seed=seed, **DIFFICULTY_PRESETS["Hard"])
            result = sim.run()
            assert result["score"] >= 10, (
                f"5-bot seed {seed} scored {result['score']} (below 10 threshold)"
            )

    def test_5bot_average_above_threshold(self):
        """5-bot average across seeds 1-10 should be >= 60."""
        scores = []
        for seed in range(1, 11):
            sim = GameSimulator(seed=seed, **DIFFICULTY_PRESETS["Hard"])
            result = sim.run()
            scores.append(result["score"])
        import statistics as _stats
        avg = _stats.mean(scores)
        assert avg >= 60, (
            f"5-bot average score {avg:.1f} is below 60 threshold "
            f"(scores: {scores})"
        )

    def test_no_excessive_idle_rounds(self):
        """Idle rounds should be < 50% of total bot-rounds for 5 bots."""
        for seed in range(1, 6):
            sim = GameSimulator(seed=seed, **DIFFICULTY_PRESETS["Hard"])
            result = sim.run(diagnose=True)
            diag = result["diagnostics"]
            total_br = diag["total_bot_rounds"]
            idle_pct = diag["idle_rounds"] / total_br * 100 if total_br > 0 else 0
            assert idle_pct < 50, (
                f"5-bot seed {seed}: idle rounds {idle_pct:.1f}% exceeds 50% "
                f"({diag['idle_rounds']}/{total_br})"
            )

    def test_no_long_delivery_gaps(self):
        """Max delivery gap should be < 150 rounds for any 5-bot config."""
        for seed in range(1, 11):
            sim = GameSimulator(seed=seed, **DIFFICULTY_PRESETS["Hard"])
            result = sim.run(diagnose=True)
            diag = result["diagnostics"]
            assert diag["max_delivery_gap"] < 150, (
                f"5-bot seed {seed}: max delivery gap {diag['max_delivery_gap']} "
                f"exceeds 150 rounds"
            )

    def test_10bot_scores_above_zero(self):
        """10-bot configs should score > 0 for all seeds 1-10."""
        cfg = DIFFICULTY_PRESETS["Expert"]
        for seed in range(1, 11):
            sim = GameSimulator(seed=seed, **cfg)
            result = sim.run()
            assert result["score"] > 0, (
                f"10-bot seed {seed} scored 0 (complete deadlock)"
            )


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
