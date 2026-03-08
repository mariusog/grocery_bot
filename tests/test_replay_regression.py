"""Replay map regression tests — deterministic, fast, catches real-world regressions.

These tests run recorded maps from live games through the planner and verify
minimum scores.  They are FAST (each takes <2s) and are NOT marked slow.

Thresholds are set at ~60% of current scores to catch catastrophic regressions
(like the T50 oscillation fix being lost, which dropped Nightmare from 124 to 46)
without being overly brittle to small optimisation changes.
"""

from pathlib import Path

import pytest

from grocery_bot.simulator.replay_simulator import ReplaySimulator


MAPS_DIR = Path(__file__).resolve().parent.parent / "maps"


def _replay_score(map_path: str) -> dict:
    """Run a replay and return the result dict."""
    sim = ReplaySimulator(map_path)
    return sim.run(verbose=False, diagnose=True)


def _all_maps() -> list[Path]:
    """Return all recorded map files sorted by name."""
    return sorted(MAPS_DIR.glob("*.json"))


# ---------------------------------------------------------------------------
# Per-map minimum score thresholds (set ~60% of known scores)
# ---------------------------------------------------------------------------
# Current baselines (2026-03-08 with T50):
#   12x10_1bot:  126
#   16x12_3bot:  153
#   22x14_5bot:  111
#   28x18_10bot:  95
#   30x18_20bot (old): 119
#   30x18_20bot (new): 124
#
# Thresholds allow headroom but catch catastrophic regressions (>40% drop).
MIN_SCORE_BY_BOTS = {
    1: 80,    # Easy: min threshold 80 (current ~126)
    3: 90,    # Medium: min threshold 90 (current ~153)
    5: 60,    # Hard: min threshold 60 (current ~111)
    10: 50,   # Expert: min threshold 50 (current ~95)
    20: 60,   # Nightmare: min threshold 60 (current 119-124)
}


class TestReplayMinimumScores:
    """Every recorded map must score above a difficulty-dependent minimum."""

    @pytest.fixture(scope="class")
    def replay_results(self) -> dict[str, dict]:
        """Run all replay maps once, shared across test methods."""
        results = {}
        for map_path in _all_maps():
            results[map_path.name] = _replay_score(str(map_path))
        return results

    def test_all_maps_above_minimum(self, replay_results):
        """No replay map should score below its difficulty threshold."""
        for name, result in replay_results.items():
            sim = ReplaySimulator(str(MAPS_DIR / name))
            num_bots = sim.num_bots
            threshold = MIN_SCORE_BY_BOTS.get(num_bots, 30)
            assert result["score"] >= threshold, (
                f"Replay {name} scored {result['score']} "
                f"(threshold: {threshold} for {num_bots} bots). "
                f"Catastrophic regression detected."
            )

    def test_nightmare_maps_no_stall(self, replay_results):
        """Nightmare maps must not stall (max delivery gap < 200 rounds)."""
        for name, result in replay_results.items():
            sim = ReplaySimulator(str(MAPS_DIR / name))
            if sim.num_bots < 20:
                continue
            diag = result["diagnostics"]
            assert diag["max_delivery_gap"] < 200, (
                f"Replay {name}: delivery gap {diag['max_delivery_gap']} rounds. "
                f"Likely stalled — bots oscillating or permanently idle."
            )

    def test_nightmare_oscillation_bounded(self, replay_results):
        """Nightmare oscillation count should stay below 10000."""
        for name, result in replay_results.items():
            sim = ReplaySimulator(str(MAPS_DIR / name))
            if sim.num_bots < 20:
                continue
            diag = result["diagnostics"]
            assert diag["oscillation_count"] < 10000, (
                f"Replay {name}: oscillation count {diag['oscillation_count']}. "
                f"Oscillation fix may be missing or broken."
            )


# ---------------------------------------------------------------------------
# Performance threshold ceilings (T61)
# ---------------------------------------------------------------------------
# Generous starting thresholds (~20% above current baselines).
# Tighten as T59/T60/T43 land improvements.
#
# Current baselines (2026-03-08):
#   1-bot:  rds/order ~20,  inv_full 0
#   3-bot:  rds/order ~19,  inv_full 8
#   5-bot:  rds/order ~23,  inv_full 80
#   10-bot: rds/order ~30,  inv_full 258
#   20-bot: rds/order ~15,  inv_full ~200
MAX_ROUNDS_PER_ORDER = {
    1: 28,     # Easy:      current ~20
    3: 24,     # Medium:    current ~19
    5: 30,     # Hard:      current ~23
    10: 40,    # Expert:    current ~30
    20: 25,    # Nightmare: current ~15
}

MAX_INV_FULL_WAITS = {
    1: 10,     # Easy:      current ~0
    3: 40,     # Medium:    current ~8
    5: 120,    # Hard:      current ~80
    10: 350,   # Expert:    current ~258
    20: 600,   # Nightmare: current ~200
}


class TestReplayPerformanceThresholds:
    """Performance ceiling tests — catch regressions in order speed and waste."""

    @pytest.fixture(scope="class")
    def replay_results(self) -> dict[str, dict]:
        """Run all replay maps once, shared across test methods."""
        results = {}
        for map_path in _all_maps():
            results[map_path.name] = _replay_score(str(map_path))
        return results

    def test_rounds_per_order_bounded(self, replay_results):
        """Avg rounds-per-order must stay below per-difficulty ceilings."""
        for name, result in replay_results.items():
            sim = ReplaySimulator(str(MAPS_DIR / name))
            num_bots = sim.num_bots
            ceiling = MAX_ROUNDS_PER_ORDER.get(num_bots, 50)
            diag = result["diagnostics"]
            avg_rpo = diag["avg_rounds_per_order"]
            assert avg_rpo <= ceiling, (
                f"Replay {name}: avg_rounds_per_order={avg_rpo:.1f} "
                f"exceeds ceiling {ceiling} for {num_bots} bots. "
                f"Order completion speed regressed."
            )

    def test_inv_full_waits_bounded(self, replay_results):
        """Inventory-full waits must stay below per-difficulty ceilings."""
        for name, result in replay_results.items():
            sim = ReplaySimulator(str(MAPS_DIR / name))
            num_bots = sim.num_bots
            ceiling = MAX_INV_FULL_WAITS.get(num_bots, 1000)
            diag = result["diagnostics"]
            inv_full = diag["inv_full_waits"]
            assert inv_full <= ceiling, (
                f"Replay {name}: inv_full_waits={inv_full} "
                f"exceeds ceiling {ceiling} for {num_bots} bots. "
                f"Inventory clearing regressed."
            )


class TestReplayNoDeadlock:
    """Replay maps must complete orders — not deadlock at 0 score."""

    def test_every_map_scores_above_zero(self):
        """All recorded maps must score > 0 (no total deadlocks)."""
        for map_path in _all_maps():
            result = _replay_score(str(map_path))
            assert result["score"] > 0, (
                f"Replay {map_path.name} scored 0 — complete deadlock."
            )

    def test_every_map_completes_at_least_one_order(self):
        """All recorded maps must complete at least 1 order."""
        for map_path in _all_maps():
            result = _replay_score(str(map_path))
            assert result["orders_completed"] >= 1, (
                f"Replay {map_path.name} completed 0 orders — deadlock."
            )
