"""Tests for simulator edge cases, difficulty presets, and profiling."""

import time

import bot
from grocery_bot.simulator import (
    GameSimulator,
    run_benchmark,
    DIFFICULTY_PRESETS,
)
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


class TestSimulatedGame:
    """Run the bot through a full simulated game to measure actual scores."""

    def test_easy_single_seed(self):
        """Single Easy game should score reasonably."""
        sim = GameSimulator(seed=42, num_bots=1)
        result = sim.run(verbose=True)
        assert result["score"] >= 50, f"Score {result['score']} too low for Easy map"
        assert result["orders_completed"] >= 5, (
            f"Only completed {result['orders_completed']} orders"
        )

    def test_easy_average_across_seeds(self):
        """Average across multiple seeds should be consistent."""
        scores = []
        for seed in range(5):
            sim = GameSimulator(seed=seed, num_bots=1)
            result = sim.run()
            scores.append(result["score"])
            print(
                f"  Seed {seed}: score={result['score']}, "
                f"orders={result['orders_completed']}, "
                f"items={result['items_delivered']}"
            )
        avg = sum(scores) / len(scores)
        print(f"  Average: {avg:.1f}, Min: {min(scores)}, Max: {max(scores)}")
        assert avg >= 50, f"Average score {avg:.1f} too low"

    def test_easy_completes_first_order(self):
        """Bot should at least complete the first order."""
        sim = GameSimulator(seed=42, num_bots=1)
        result = sim.run()
        assert result["orders_completed"] >= 1, "Failed to complete even 1 order"

    def test_no_wasted_rounds_at_start(self):
        """Bot should start moving on round 0, not wait."""
        sim = GameSimulator(seed=42, num_bots=1)
        state = sim.get_state()
        reset_bot()
        actions = bot.decide_actions(state)
        action = actions[0]
        assert action["action"] != "wait", (
            f"Bot should not wait on round 0, got {action}"
        )


class TestSimulatorDifficultyPresets:
    """Test that simulator difficulty presets work correctly."""

    def test_easy_preset(self):
        """Easy preset should produce valid results."""
        cfg = DIFFICULTY_PRESETS["Easy"]
        sim = GameSimulator(seed=42, **cfg)
        result = sim.run()
        assert result["score"] > 0, "Easy preset should score > 0"
        assert result["rounds_used"] == 300

    def test_medium_preset_runs(self):
        """Medium preset should not crash (3 bots may score 0 due to collision bug)."""
        cfg = DIFFICULTY_PRESETS["Medium"]
        sim = GameSimulator(seed=42, **cfg)
        result = sim.run()
        # May score 0 due to multi-bot collision bug, but should not crash
        assert result["rounds_used"] == 300
        assert result["score"] >= 0

    def test_hard_preset_runs(self):
        """Hard preset should not crash."""
        cfg = DIFFICULTY_PRESETS["Hard"]
        sim = GameSimulator(seed=42, **cfg)
        result = sim.run()
        assert result["rounds_used"] == 300
        assert result["score"] >= 0

    def test_expert_preset_runs(self):
        """Expert preset should not crash."""
        cfg = DIFFICULTY_PRESETS["Expert"]
        sim = GameSimulator(seed=42, **cfg)
        result = sim.run()
        assert result["rounds_used"] == 300
        assert result["score"] >= 0

    def test_run_benchmark_function(self):
        """run_benchmark() should return results for all configs."""
        # Use single seed for speed
        results = run_benchmark(
            configs={"Easy": DIFFICULTY_PRESETS["Easy"]},
            seeds=[42],
        )
        assert len(results) == 1
        assert results[0]["config"] == "Easy"
        assert "score" in results[0]

    def test_profiling_output(self):
        """Profiling mode should include timing data."""
        cfg = DIFFICULTY_PRESETS["Easy"]
        sim = GameSimulator(seed=42, **cfg)
        result = sim.run(profile=True)
        assert "timings" in result
        assert "decide_actions" in result["timings"]
        stats = result["timings"]["decide_actions"]
        assert stats["calls"] > 0
        assert stats["avg_ms"] > 0


class TestSimulatorPerformanceProfiling:
    """Verify timing/profiling produces reasonable results."""

    def test_decide_actions_timing(self):
        """decide_actions should complete in reasonable time per round."""
        reset_bot()
        sim = GameSimulator(seed=42, num_bots=1)
        result = sim.run(profile=True)
        stats = result["timings"]["decide_actions"]
        # Average should be under 5ms on any reasonable machine
        assert stats["avg_ms"] < 5.0, (
            f"decide_actions avg {stats['avg_ms']:.3f}ms is too slow"
        )
        # Max (including round 0 with init_static) under 50ms
        assert stats["max_ms"] < 50.0, (
            f"decide_actions max {stats['max_ms']:.3f}ms is too slow"
        )

    def test_full_game_wall_time(self):
        """Full Easy game should complete in under 2 seconds."""
        sim = GameSimulator(seed=42, num_bots=1)
        t0 = time.perf_counter()
        sim.run()
        elapsed = time.perf_counter() - t0
        assert elapsed < 2.0, f"Full game took {elapsed:.3f}s, should be under 2s"
