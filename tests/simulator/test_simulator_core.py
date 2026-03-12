"""Tests for simulator edge cases and physics."""

import time

import bot
from grocery_bot.simulator import GameSimulator
from tests.conftest import reset_bot


class TestSimulatorEdgeCases:
    """Test simulator edge cases for coverage."""

    def test_large_map_aisle_generation(self):
        """Simulator generates correct aisles for larger maps."""
        sim = GameSimulator(seed=1, width=16, height=10)
        assert len(sim.item_shelves) > 0

    def test_extra_large_map(self):
        sim = GameSimulator(seed=1, width=22, height=12)
        assert len(sim.item_shelves) > 0

    def test_huge_map(self):
        sim = GameSimulator(seed=1, width=26, height=14)
        assert len(sim.item_shelves) > 0

    def test_blocked_by_wall(self):
        """Simulator correctly blocks movement into walls."""
        sim = GameSimulator(seed=42, num_bots=1)
        sim.walls = [[5, 5]]
        assert sim._is_blocked(5, 5) is True

    def test_blocked_by_other_bot(self):
        sim = GameSimulator(seed=42, num_bots=2)
        pos = sim.bots[0]["position"]
        assert sim._is_blocked(pos[0], pos[1], exclude_bot_id=1) is True

    def test_pickup_too_far(self):
        """Pickup fails when bot is not adjacent to item."""
        sim = GameSimulator(seed=42, num_bots=1)
        b = sim.bots[0]
        item = sim.items_on_map[0]
        # Move bot far from item
        b["position"] = [0, 0]
        action = {"action": "pick_up", "item_id": item["id"]}
        sim._apply_action(b, action)
        assert len(b["inventory"]) == 0

    def test_pickup_nonexistent_item(self):
        sim = GameSimulator(seed=42, num_bots=1)
        b = sim.bots[0]
        action = {"action": "pick_up", "item_id": "nonexistent"}
        sim._apply_action(b, action)
        assert len(b["inventory"]) == 0

    def test_pickup_full_inventory(self):
        sim = GameSimulator(seed=42, num_bots=1)
        b = sim.bots[0]
        b["inventory"] = ["a", "b", "c"]
        item = sim.items_on_map[0]
        action = {"action": "pick_up", "item_id": item["id"]}
        sim._apply_action(b, action)
        assert len(b["inventory"]) == 3

    def test_dropoff_wrong_position(self):
        sim = GameSimulator(seed=42, num_bots=1)
        b = sim.bots[0]
        b["inventory"] = ["milk"]
        b["position"] = [0, 0]  # not at drop-off
        action = {"action": "drop_off"}
        sim._apply_action(b, action)
        assert len(b["inventory"]) == 1  # nothing delivered

    def test_dropoff_empty_inventory(self):
        sim = GameSimulator(seed=42, num_bots=1)
        b = sim.bots[0]
        b["position"] = list(sim.drop_off)
        b["inventory"] = []
        action = {"action": "drop_off"}
        sim._apply_action(b, action)
        assert sim.score == 0

    def test_verbose_run(self):
        """Simulator runs in verbose mode without errors."""
        sim = GameSimulator(seed=42, num_bots=1, max_rounds=100)
        result = sim.run(verbose=True)
        assert result["rounds_used"] == 100

    def test_move_blocked_by_boundary(self):
        """Bot can't move out of bounds."""
        sim = GameSimulator(seed=42, num_bots=1)
        b = sim.bots[0]
        b["position"] = [0, 0]
        action = {"action": "move_left"}
        sim._apply_action(b, action)
        assert b["position"] == [0, 0]


class TestSimulatorPerformanceProfiling:
    """Verify timing/profiling produces reasonable results."""

    def test_decide_actions_timing(self):
        """decide_actions should complete in reasonable time per round."""
        reset_bot()
        sim = GameSimulator(seed=42, num_bots=1)
        result = sim.run(profile=True)
        stats = result["timings"]["decide_actions"]
        # Average should be under 5ms on any reasonable machine
        assert stats["avg_ms"] < 5.0, f"decide_actions avg {stats['avg_ms']:.3f}ms is too slow"
        # Max (including round 0 with init_static) under 50ms
        assert stats["max_ms"] < 50.0, f"decide_actions max {stats['max_ms']:.3f}ms is too slow"

    def test_full_game_wall_time(self):
        """Full Easy game should complete in under 2 seconds."""
        sim = GameSimulator(seed=42, num_bots=1)
        t0 = time.perf_counter()
        sim.run()
        elapsed = time.perf_counter() - t0
        assert elapsed < 2.0, f"Full game took {elapsed:.3f}s, should be under 2s"
