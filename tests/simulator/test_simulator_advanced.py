"""Tests for simulator edge cases, difficulty presets, and profiling."""

import os

from grocery_bot.simulator import (
    DIFFICULTY_PRESETS,
    GameSimulator,
    profile_congestion,
)


class TestOrderCascadeDelivery:
    """Items for next order already in inventory when current order completes."""

    def test_cascade_delivery_in_simulator(self):
        """Verify the simulator cascade logic works: completing order N
        auto-delivers matching items for order N+1."""
        sim = GameSimulator(seed=42, num_bots=1)
        # Manually set up a cascade scenario
        sim.orders = [
            {
                "id": "order_0",
                "items_required": ["milk"],
                "items_delivered": [],
                "complete": False,
            },
            {
                "id": "order_1",
                "items_required": ["cheese"],
                "items_delivered": [],
                "complete": False,
            },
        ]
        sim.active_order_idx = 0
        # Bot at dropoff with milk (for order 0) and cheese (for order 1)
        sim.bots = [
            {"id": 0, "position": list(sim.drop_off), "inventory": ["milk", "cheese"]}
        ]
        # Perform dropoff
        sim._do_dropoff(sim.bots[0])
        # Order 0 should be complete, and cheese should cascade to order 1
        assert sim.orders[0]["complete"], "Order 0 should be complete"
        assert sim.orders[1]["complete"], "Order 1 should cascade-complete"
        assert sim.orders_completed == 2
        assert sim.items_delivered == 2
        assert sim.score == 2 + 5 + 5  # 2 items + 2 order bonuses = 12
        assert sim.bots[0]["inventory"] == []

    def test_cascade_with_leftover_items(self):
        """Cascade should leave items that don't match the next order."""
        sim = GameSimulator(seed=42, num_bots=1)
        sim.orders = [
            {
                "id": "order_0",
                "items_required": ["milk"],
                "items_delivered": [],
                "complete": False,
            },
            {
                "id": "order_1",
                "items_required": ["bread"],
                "items_delivered": [],
                "complete": False,
            },
        ]
        sim.active_order_idx = 0
        sim.bots = [
            {"id": 0, "position": list(sim.drop_off), "inventory": ["milk", "cheese"]}
        ]
        sim._do_dropoff(sim.bots[0])
        assert sim.orders[0]["complete"]
        assert not sim.orders[1]["complete"], "Order 1 needs bread, not cheese"
        assert sim.bots[0]["inventory"] == ["cheese"], (
            "Cheese should remain in inventory"
        )


class TestDiagnosticMode:
    """Tests for the simulator diagnostic mode."""

    def test_diagnose_returns_diagnostics_key(self):
        """Running with diagnose=True should include diagnostics in result."""
        sim = GameSimulator(seed=42, num_bots=1)
        result = sim.run(diagnose=True)
        assert "diagnostics" in result
        diag = result["diagnostics"]
        assert "idle_rounds" in diag
        assert "stuck_rounds" in diag
        assert "max_delivery_gap" in diag
        assert "oscillation_count" in diag
        assert "avg_bots_idle" in diag
        assert "total_bot_rounds" in diag

    def test_diagnose_values_are_sensible(self):
        """Diagnostic values should be non-negative and within bounds."""
        sim = GameSimulator(seed=42, num_bots=3)
        result = sim.run(diagnose=True)
        diag = result["diagnostics"]
        assert diag["idle_rounds"] >= 0
        assert diag["stuck_rounds"] >= 0
        assert diag["max_delivery_gap"] >= 0
        assert diag["oscillation_count"] >= 0
        assert diag["avg_bots_idle"] >= 0
        assert diag["total_bot_rounds"] == result["rounds_used"] * 3

    def test_diagnose_does_not_affect_score(self):
        """Score should be the same with or without diagnostics."""
        sim1 = GameSimulator(seed=42, num_bots=3)
        result1 = sim1.run()
        sim2 = GameSimulator(seed=42, num_bots=3)
        result2 = sim2.run(diagnose=True)
        assert result1["score"] == result2["score"]

    def test_single_bot_no_stuck_no_idle(self):
        """A single active bot should have very few stuck or idle rounds."""
        sim = GameSimulator(seed=42, num_bots=1)
        result = sim.run(diagnose=True)
        diag = result["diagnostics"]
        # Single bot should be efficient — less than 10% idle
        total = diag["total_bot_rounds"]
        idle_pct = diag["idle_rounds"] / total * 100 if total > 0 else 0
        assert idle_pct < 10, f"Single bot idle {idle_pct:.1f}% is too high"


class TestLocalLogNaming:
    """Local simulator logs should expose difficulty in the filename."""

    def test_local_log_path_includes_difficulty_slug(self, monkeypatch, tmp_path):
        from grocery_bot.simulator import sim_logging as log_mod

        monkeypatch.setattr(log_mod, "_LOG_DIR", str(tmp_path))
        sim = GameSimulator(seed=42, **DIFFICULTY_PRESETS["Easy"])
        result = sim.run(log=True)

        basename = os.path.basename(result["log_path"])
        assert basename.startswith("local_easy_12x10_1bot_")


class TestCongestionProfiler:
    """Tests for the profile_congestion function."""

    def test_profile_congestion_returns_results(self):
        """profile_congestion should return a list of result dicts."""
        results = profile_congestion(num_bots=2, seeds=[1, 2])
        assert len(results) == 2
        for r in results:
            assert "score" in r
            assert "diagnostics" in r
            assert "seed" in r
            assert "num_bots" in r

    def test_profile_congestion_5bot(self):
        """Profile 5 bots for seed 1 and verify output structure."""
        results = profile_congestion(num_bots=5, seeds=[1])
        assert len(results) == 1
        assert results[0]["num_bots"] == 5
        assert results[0]["diagnostics"]["total_bot_rounds"] > 0
