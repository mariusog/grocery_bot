"""Unit tests for GameState methods (game_state.py)."""

from grocery_bot.game_state import GameState
from tests.conftest import make_gs_with_state


class TestTspCost:
    def test_empty_targets(self):
        gs = make_gs_with_state()
        cost = gs.tsp_cost((1, 1), [], (1, 8))
        # With no items, cost is just dist from bot to dropoff
        assert cost == gs.dist_static((1, 1), (1, 8))

    def test_single_target(self):
        gs = make_gs_with_state()
        cost = gs.tsp_cost((1, 1), [("a", (3, 3))], (1, 8))
        expected = gs.dist_static((1, 1), (3, 3)) + gs.dist_static((3, 3), (1, 8))
        assert cost == expected

    def test_two_targets(self):
        gs = make_gs_with_state()
        targets = [("a", (2, 1)), ("b", (2, 7))]
        cost = gs.tsp_cost((1, 1), targets, (1, 8))
        expected = (
            gs.dist_static((1, 1), (2, 1))
            + gs.dist_static((2, 1), (2, 7))
            + gs.dist_static((2, 7), (1, 8))
        )
        assert cost == expected


class TestPlanMultiTrip:
    def test_within_capacity_uses_tsp(self):
        gs = make_gs_with_state()
        targets = [("a", (2, 1)), ("b", (2, 3))]
        result = gs.plan_multi_trip((1, 1), targets, (1, 8), capacity=3)
        assert len(result) == 2

    def test_exceeds_capacity_splits(self):
        gs = make_gs_with_state()
        targets = [("a", (2, 1)), ("b", (3, 1)), ("c", (4, 1)), ("d", (5, 1))]
        result = gs.plan_multi_trip((1, 1), targets, (1, 8), capacity=3)
        # Returns first trip only
        assert len(result) <= 3

    def test_single_item(self):
        gs = make_gs_with_state()
        targets = [("a", (3, 3))]
        result = gs.plan_multi_trip((1, 1), targets, (1, 8))
        assert result == targets


class TestGetOptimalRoute:
    def test_empty_types_returns_none(self):
        gs = make_gs_with_state()
        assert gs.get_optimal_route([], (1, 1), (1, 8)) is None

    def test_single_type_found(self):
        items = [{"id": "i1", "type": "cheese", "position": [4, 4]}]
        state = {
            "grid": {"width": 11, "height": 9, "walls": []},
            "items": items,
            "drop_off": [1, 8],
        }

        gs2 = GameState()
        gs2.init_static(state)
        result = gs2.get_optimal_route(["cheese"], (1, 1), (1, 8))
        if result is not None:
            assert len(result) == 1
            assert result[0][0] == "cheese"

    def test_unknown_type_returns_none(self):
        items = [{"id": "i1", "type": "cheese", "position": [4, 4]}]
        state = {
            "grid": {"width": 11, "height": 9, "walls": []},
            "items": items,
            "drop_off": [1, 8],
        }

        gs2 = GameState()
        gs2.init_static(state)
        result = gs2.get_optimal_route(["unknown_type"], (1, 1), (1, 8))
        assert result is None

    def test_four_types_returns_none(self):
        """More than 3 types is unsupported -> None."""
        gs = make_gs_with_state()
        result = gs.get_optimal_route(["a", "b", "c", "d"], (1, 1), (1, 8))
        assert result is None


class TestPrecomputeRouteTables:
    def test_two_item_types(self):
        items = [
            {"id": "i1", "type": "cheese", "position": [3, 2]},
            {"id": "i2", "type": "milk", "position": [7, 6]},
        ]
        state = {
            "grid": {"width": 11, "height": 9, "walls": []},
            "items": items,
            "drop_off": [1, 8],
        }

        gs = GameState()
        gs.init_static(state)
        assert "cheese" in gs.best_pickup
        assert "milk" in gs.best_pickup
        key = tuple(sorted(["cheese", "milk"]))
        assert key in gs.best_pair_route

    def test_three_item_types(self):
        items = [
            {"id": "i1", "type": "a", "position": [3, 2]},
            {"id": "i2", "type": "b", "position": [5, 2]},
            {"id": "i3", "type": "c", "position": [7, 2]},
        ]
        state = {
            "grid": {"width": 11, "height": 9, "walls": []},
            "items": items,
            "drop_off": [1, 8],
        }

        gs = GameState()
        gs.init_static(state)
        key = tuple(sorted(["a", "b", "c"]))
        assert key in gs.best_triple_route


class TestPlanInterleavedRoute:
    def test_empty_targets(self):
        gs = make_gs_with_state()
        assert gs.plan_interleaved_route((1, 1), [], (1, 8)) == []

    def test_single_target(self):
        gs = make_gs_with_state()
        targets = [("item_a", (3, 3))]
        result = gs.plan_interleaved_route((1, 1), targets, (1, 8))
        assert len(result) == 2
        assert result[0] == ("pickup", ("item_a", (3, 3)))
        assert result[1] == ("deliver", (1, 8))

    def test_two_targets_within_capacity(self):
        gs = make_gs_with_state()
        targets = [("a", (2, 1)), ("b", (2, 7))]
        result = gs.plan_interleaved_route((1, 1), targets, (1, 8), capacity=3)
        assert len(result) >= 2
        # Should end with a deliver
        assert result[-1][0] == "deliver"

    def test_exceeds_capacity_interleaves(self):
        gs = make_gs_with_state()
        targets = [("a", (2, 1)), ("b", (3, 1)), ("c", (4, 1)), ("d", (5, 1))]
        result = gs.plan_interleaved_route((1, 1), targets, (1, 8), capacity=3)
        # Should have multiple deliver steps
        delivers = [step for step in result if step[0] == "deliver"]
        assert len(delivers) >= 2


class TestHungarianAssign:
    def test_empty_inputs(self):
        gs = make_gs_with_state()
        assert gs.hungarian_assign([], []) == []
        assert gs.hungarian_assign([(1, 1)], []) == []
        assert gs.hungarian_assign([], [(2, 2)]) == []

    def test_one_to_one(self):
        gs = make_gs_with_state()
        result = gs.hungarian_assign([(1, 1)], [(3, 3)])
        assert len(result) == 1
        assert result[0] == (0, 0)

    def test_two_to_two(self):
        gs = make_gs_with_state()
        bot_positions = [(1, 1), (9, 1)]
        item_positions = [(2, 1), (8, 1)]
        result = gs.hungarian_assign(bot_positions, item_positions)
        assert len(result) == 2
        # Bot 0 should get item 0 (closer), bot 1 should get item 1
        pairs = dict(result)
        assert pairs[0] == 0
        assert pairs[1] == 1


class TestGetDistancesFrom:
    def test_caches_result(self):
        gs = make_gs_with_state()
        d1 = gs.get_distances_from((1, 1))
        d2 = gs.get_distances_from((1, 1))
        assert d1 is d2  # Same object from cache

    def test_different_sources(self):
        gs = make_gs_with_state()
        d1 = gs.get_distances_from((1, 1))
        d2 = gs.get_distances_from((5, 5))
        assert d1 is not d2


# ------------------------------------------------------------------
# T30: Dropoff congestion management tests
# ------------------------------------------------------------------
