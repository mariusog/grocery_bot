"""Replay map regression tests — deterministic, catches real-world regressions.

By default, only the latest day's maps are replayed (fast, ~5 maps).
Use ``--run-all-maps`` or ``-m slow`` to include all historical maps.

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


def _latest_maps() -> list[Path]:
    """Return only the most recent day's map files.

    Map files are named ``YYYY-MM-DD_WxH_Nbot.json``.  This picks the
    latest date prefix and returns all maps from that day.
    """
    all_maps = _all_maps()
    if not all_maps:
        return []
    # Extract date prefix (first 10 chars of filename: "2026-03-11")
    latest_date = all_maps[-1].name[:10]
    return [m for m in all_maps if m.name.startswith(latest_date)]


# ---------------------------------------------------------------------------
# Per-map minimum score thresholds (set ~60% of known scores)
# ---------------------------------------------------------------------------
MIN_SCORE_BY_BOTS = {
    1: 80,  # Easy: min threshold 80 (current ~126)
    3: 90,  # Medium: min threshold 90 (current ~153)
    5: 60,  # Hard: min threshold 60 (current ~111)
    10: 50,  # Expert: min threshold 50 (current ~95)
    20: 60,  # Nightmare: min threshold 60 (current 119-124)
}


def _run_maps(maps: list[Path]) -> dict[str, dict]:
    """Run replays for a list of maps and return results by name."""
    results = {}
    for map_path in maps:
        results[map_path.name] = _replay_score(str(map_path))
    return results


def _check_minimum_scores(replay_results: dict[str, dict]) -> None:
    """Assert all results exceed difficulty-dependent minimums."""
    for name, result in replay_results.items():
        sim = ReplaySimulator(str(MAPS_DIR / name))
        num_bots = sim.num_bots
        threshold = MIN_SCORE_BY_BOTS.get(num_bots, 30)
        assert result["score"] >= threshold, (
            f"Replay {name} scored {result['score']} "
            f"(threshold: {threshold} for {num_bots} bots). "
            f"Catastrophic regression detected."
        )


class TestReplayLatest:
    """Latest-day replay tests — run by default (fast, ~5 maps)."""

    @pytest.fixture(scope="class")
    def replay_results(self) -> dict[str, dict]:
        return _run_maps(_latest_maps())

    def test_latest_maps_above_minimum(self, replay_results: dict[str, dict]) -> None:
        _check_minimum_scores(replay_results)

    def test_latest_nightmare_no_stall(self, replay_results: dict[str, dict]) -> None:
        for name, result in replay_results.items():
            sim = ReplaySimulator(str(MAPS_DIR / name))
            if sim.num_bots < 20:
                continue
            diag = result["diagnostics"]
            assert diag["max_delivery_gap"] < 200, (
                f"Replay {name}: delivery gap {diag['max_delivery_gap']} rounds."
            )

    def test_latest_no_deadlock(self, replay_results: dict[str, dict]) -> None:
        for name, result in replay_results.items():
            assert result["score"] > 0, f"Replay {name} scored 0 — deadlock."
            assert result["orders_completed"] >= 1, f"Replay {name} completed 0 orders — deadlock."


# ---------------------------------------------------------------------------
# Full history tests — marked slow, only run with -m slow or --run-all-maps
# ---------------------------------------------------------------------------
MAX_ROUNDS_PER_ORDER = {
    1: 28,
    3: 26,
    5: 30,
    10: 40,
    20: 25,
}
MAX_INV_FULL_WAITS = {
    1: 10,
    3: 40,
    5: 120,
    10: 400,
    20: 600,
}


@pytest.mark.slow
class TestReplayAllMaps:
    """Full history regression — all recorded maps across all days."""

    @pytest.fixture(scope="class")
    def replay_results(self) -> dict[str, dict]:
        return _run_maps(_all_maps())

    def test_all_maps_above_minimum(self, replay_results: dict[str, dict]) -> None:
        _check_minimum_scores(replay_results)

    def test_nightmare_oscillation_bounded(self, replay_results: dict[str, dict]) -> None:
        for name, result in replay_results.items():
            sim = ReplaySimulator(str(MAPS_DIR / name))
            if sim.num_bots < 20:
                continue
            diag = result["diagnostics"]
            assert diag["oscillation_count"] < 10000, (
                f"Replay {name}: oscillation count {diag['oscillation_count']}."
            )

    def test_rounds_per_order_bounded(self, replay_results: dict[str, dict]) -> None:
        for name, result in replay_results.items():
            sim = ReplaySimulator(str(MAPS_DIR / name))
            num_bots = sim.num_bots
            ceiling = MAX_ROUNDS_PER_ORDER.get(num_bots, 50)
            diag = result["diagnostics"]
            avg_rpo = diag["avg_rounds_per_order"]
            assert avg_rpo <= ceiling, (
                f"Replay {name}: avg_rounds_per_order={avg_rpo:.1f} "
                f"exceeds ceiling {ceiling} for {num_bots} bots."
            )

    def test_inv_full_waits_bounded(self, replay_results: dict[str, dict]) -> None:
        for name, result in replay_results.items():
            sim = ReplaySimulator(str(MAPS_DIR / name))
            num_bots = sim.num_bots
            ceiling = MAX_INV_FULL_WAITS.get(num_bots, 1000)
            diag = result["diagnostics"]
            inv_full = diag["inv_full_waits"]
            assert inv_full <= ceiling, (
                f"Replay {name}: inv_full_waits={inv_full} "
                f"exceeds ceiling {ceiling} for {num_bots} bots."
            )
