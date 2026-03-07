"""Unit tests for GameState methods (game_state.py)."""

from grocery_bot.game_state import GameState
from tests.conftest import make_gs_with_state


def _make_gs_with_dropoff(items=None, walls=None, width=11, height=9, drop_off=None):
    """Create a GameState with dropoff zones precomputed."""
    state = {
        "grid": {
            "width": width,
            "height": height,
            "walls": walls or [],
        },
        "items": items or [],
        "drop_off": drop_off or [1, 8],
    }
    gs = GameState()
    gs.init_static(state)
    return gs


class TestDistStatic:
    def test_same_position_returns_zero(self):
        gs = make_gs_with_state()
        assert gs.dist_static((3, 3), (3, 3)) == 0

    def test_adjacent_positions_return_one(self):
        gs = make_gs_with_state()
        assert gs.dist_static((3, 3), (4, 3)) == 1
        assert gs.dist_static((3, 3), (3, 4)) == 1

    def test_unreachable_returns_inf(self):
        """A position surrounded by walls is unreachable."""
        gs = make_gs_with_state(
            walls=[[4, 3], [4, 5], [3, 4], [5, 4]],
            width=11,
            height=9,
        )
        # (4, 4) is enclosed by walls on all 4 sides
        assert gs.dist_static((1, 1), (4, 4)) == float("inf")

    def test_distance_around_wall(self):
        """Distance should route around a wall."""
        gs = make_gs_with_state(
            walls=[[3, 3]],
            width=11,
            height=9,
        )
        # Direct would be 2 steps (2,3)->(3,3)->(4,3), but (3,3) is wall
        d = gs.dist_static((2, 3), (4, 3))
        assert d == 4  # must go around

    def test_distance_caching(self):
        gs = make_gs_with_state()
        d1 = gs.dist_static((1, 1), (5, 5))
        d2 = gs.dist_static((1, 1), (5, 5))
        assert d1 == d2
        # The BFS-all cache should have been populated
        assert (1, 1) in gs.dist_cache


class TestFindBestItemTarget:
    def test_finds_adjacent_cell(self):
        items = [{"id": "i1", "type": "cheese", "position": [4, 4]}]
        gs = make_gs_with_state(items=items)
        cell, d = gs.find_best_item_target((3, 4), {"position": [4, 4]})
        assert cell is not None
        assert d >= 0

    def test_closest_adjacent_cell_chosen(self):
        items = [{"id": "i1", "type": "cheese", "position": [4, 4]}]
        gs = make_gs_with_state(items=items)
        # Bot at (3, 4) — adjacent cell (3, 4) is distance 0
        cell, d = gs.find_best_item_target((3, 4), {"position": [4, 4]})
        assert cell == (3, 4)
        assert d == 0

    def test_no_adjacent_cells_returns_none(self):
        """Item surrounded by other items/walls has no adjacent walkable cell."""
        items = [
            {"id": "i0", "type": "a", "position": [4, 4]},
            {"id": "i1", "type": "b", "position": [3, 4]},
            {"id": "i2", "type": "c", "position": [5, 4]},
            {"id": "i3", "type": "d", "position": [4, 3]},
            {"id": "i4", "type": "e", "position": [4, 5]},
        ]
        gs = make_gs_with_state(items=items)
        cell, d = gs.find_best_item_target((1, 1), {"position": [4, 4]})
        assert cell is None
        assert d == float("inf")


class TestAdjCache:
    def test_adj_cache_populated_on_init(self):
        items = [{"id": "i1", "type": "cheese", "position": [4, 4]}]
        gs = make_gs_with_state(items=items)
        assert (4, 4) in gs.adj_cache
        # Item at (4,4) should have walkable neighbors
        assert len(gs.adj_cache[(4, 4)]) > 0

    def test_adj_cache_excludes_walls(self):
        items = [{"id": "i1", "type": "cheese", "position": [4, 4]}]
        gs = make_gs_with_state(items=items, walls=[[3, 4]])
        adj = gs.adj_cache[(4, 4)]
        assert (3, 4) not in adj


class TestTspRoute:
    def test_single_item_returns_unchanged(self):
        gs = make_gs_with_state()
        targets = [({"id": "i1"}, (3, 3))]
        result = gs.tsp_route((1, 1), targets, (1, 8))
        assert result == targets

    def test_two_items_optimal_ordering(self):
        gs = make_gs_with_state()
        # Bot at (1,1), drop_off at (1,8)
        # Item A at (2,1) — close to bot
        # Item B at (2,7) — close to dropoff
        targets = [
            ({"id": "a"}, (2, 7)),  # far from bot
            ({"id": "b"}, (2, 1)),  # close to bot
        ]
        result = gs.tsp_route((1, 1), targets, (1, 8))
        # Optimal: pick up close one first (b at 2,1), then far one (a at 2,7)
        assert result[0][0]["id"] == "b"
        assert result[1][0]["id"] == "a"

    def test_three_items_returns_all(self):
        gs = make_gs_with_state()
        targets = [
            ({"id": "a"}, (2, 1)),
            ({"id": "b"}, (5, 1)),
            ({"id": "c"}, (8, 1)),
        ]
        result = gs.tsp_route((1, 1), targets, (1, 8))
        assert len(result) == 3
        ids = {r[0]["id"] for r in result}
        assert ids == {"a", "b", "c"}


class TestAssignItemsToBots:
    def test_one_bot_one_item(self):
        items = [{"id": "i1", "type": "cheese", "position": [4, 4]}]
        gs = make_gs_with_state(items=items)
        assignable = [(0, (3, 4), 1)]
        result = gs.assign_items_to_bots(assignable, items)
        assert 0 in result
        assert len(result[0]) == 1

    def test_two_bots_two_items_assigns_closest(self):
        items = [
            {"id": "i1", "type": "cheese", "position": [2, 4]},
            {"id": "i2", "type": "milk", "position": [8, 4]},
        ]
        gs = make_gs_with_state(items=items)
        # Bot 0 near item i1, bot 1 near item i2
        assignable = [(0, (1, 4), 1), (1, (9, 4), 1)]
        result = gs.assign_items_to_bots(assignable, items)
        assert result.get(0, [{}])[0]["id"] == "i1"
        assert result.get(1, [{}])[0]["id"] == "i2"

    def test_empty_inputs(self):
        gs = make_gs_with_state()
        assert gs.assign_items_to_bots([], []) == {}

    def test_slot_limit_respected(self):
        items = [
            {"id": "i1", "type": "a", "position": [4, 2]},
            {"id": "i2", "type": "b", "position": [4, 4]},
            {"id": "i3", "type": "c", "position": [4, 6]},
        ]
        gs = make_gs_with_state(items=items)
        # Bot has 1 slot
        assignable = [(0, (3, 4), 1)]
        result = gs.assign_items_to_bots(assignable, items)
        assert len(result.get(0, [])) == 1


class TestInitStatic:
    def test_blocked_includes_walls(self):
        gs = make_gs_with_state(walls=[[3, 3], [5, 5]])
        assert (3, 3) in gs.blocked_static
        assert (5, 5) in gs.blocked_static

    def test_blocked_includes_item_positions(self):
        items = [{"id": "i1", "type": "cheese", "position": [4, 4]}]
        gs = make_gs_with_state(items=items)
        assert (4, 4) in gs.blocked_static

    def test_blocked_includes_borders(self):
        gs = make_gs_with_state(width=11, height=9)
        assert (-1, 0) in gs.blocked_static
        assert (11, 0) in gs.blocked_static
        assert (0, -1) in gs.blocked_static
        assert (0, 9) in gs.blocked_static

    def test_grid_dimensions_stored(self):
        gs = make_gs_with_state(width=15, height=12)
        assert gs.grid_width == 15
        assert gs.grid_height == 12


class TestComputeIdleSpots:
    def test_idle_spots_on_corridor(self):
        """Idle spots should be at walkway columns on corridor rows."""
        items = [
            {"id": "i1", "type": "a", "position": [3, 2]},
            {"id": "i2", "type": "b", "position": [3, 6]},
            {"id": "i3", "type": "c", "position": [5, 2]},
            {"id": "i4", "type": "d", "position": [5, 6]},
        ]
        gs = make_gs_with_state(items=items, width=11, height=9)
        # Should have some idle spots computed
        assert len(gs.idle_spots) > 0

    def test_idle_spots_not_blocked(self):
        items = [
            {"id": "i1", "type": "a", "position": [3, 2]},
            {"id": "i2", "type": "b", "position": [5, 2]},
        ]
        gs = make_gs_with_state(items=items, width=11, height=9)
        for spot in gs.idle_spots:
            assert spot not in gs.blocked_static

    def test_no_items_no_idle_spots(self):
        gs = make_gs_with_state(items=[], width=11, height=9)
        assert gs.idle_spots == []


class TestReset:
    def test_reset_clears_all_state(self):
        gs = make_gs_with_state(items=[{"id": "i1", "type": "a", "position": [4, 4]}])
        gs.blacklisted_items.add("i1")
        gs.pickup_fail_count["i1"] = 3
        gs.delivery_queue.append(0)
        gs.reset()
        assert gs.blocked_static is None
        assert gs.dist_cache == {}
        assert gs.adj_cache == {}
        assert gs.blacklisted_items == set()
        assert gs.pickup_fail_count == {}
        assert gs.delivery_queue == []
        assert gs.idle_spots == []
        assert gs.grid_width == 0

    def test_reset_then_reinit(self):
        gs = make_gs_with_state(items=[{"id": "i1", "type": "a", "position": [4, 4]}])
        gs.reset()
        assert gs.blocked_static is None
        # Reinitialize
        state = {"grid": {"width": 11, "height": 9, "walls": []}, "items": []}
        gs.init_static(state)
        assert gs.blocked_static is not None


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
        from grocery_bot.game_state import GameState

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
        from grocery_bot.game_state import GameState

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
        from grocery_bot.game_state import GameState

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
        from grocery_bot.game_state import GameState

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


class TestPrecomputeDropoffZones:
    def test_dropoff_adjacents_populated(self):
        gs = _make_gs_with_dropoff()
        assert len(gs.dropoff_adjacents) > 0

    def test_dropoff_adjacents_are_walkable(self):
        gs = _make_gs_with_dropoff()
        for adj in gs.dropoff_adjacents:
            assert adj not in gs.blocked_static

    def test_dropoff_approach_cells_within_radius(self):
        from grocery_bot.game_state import DROPOFF_CONGESTION_RADIUS
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        for cell in gs.dropoff_approach_cells:
            d = gs.dist_static(cell, drop_off)
            assert 0 < d <= DROPOFF_CONGESTION_RADIUS

    def test_dropoff_approach_set_matches_list(self):
        gs = _make_gs_with_dropoff()
        # approach_set includes the dropoff itself plus all approach cells
        expected = set(gs.dropoff_approach_cells) | {gs.drop_off_pos}
        assert gs.dropoff_approach_set == expected

    def test_dropoff_wait_cells_at_correct_distance(self):
        from grocery_bot.game_state import DROPOFF_WAIT_DISTANCE
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        for cell in gs.dropoff_wait_cells:
            d = gs.dist_static(cell, drop_off)
            assert d == DROPOFF_WAIT_DISTANCE

    def test_dropoff_zones_empty_without_drop_off_key(self):
        """When state has no drop_off key, zones are not computed."""
        gs = make_gs_with_state()
        assert gs.dropoff_adjacents == []
        assert gs.dropoff_approach_cells == []
        assert gs.dropoff_wait_cells == []

    def test_walled_dropoff_has_fewer_adjacents(self):
        """Dropoff surrounded by walls on 2 sides has fewer adjacents."""
        # Drop_off at (1, 8), wall at (0, 8) and (2, 8)
        gs = _make_gs_with_dropoff(walls=[[0, 8], [2, 8]])
        # Only vertical neighbors could be adjacent
        for adj in gs.dropoff_adjacents:
            assert adj not in {(0, 8), (2, 8)}


class TestGetDropoffApproachTarget:
    def test_closest_bot_goes_directly(self):
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        delivering = [(0, (1, 7)), (1, (5, 5))]
        target, should_wait = gs.get_dropoff_approach_target(0, (1, 7), drop_off, delivering)
        assert target == drop_off
        assert should_wait is False

    def test_far_bot_gets_wait_target(self):
        from grocery_bot.game_state import MAX_APPROACH_SLOTS
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        # Create enough closer bots to fill approach slots
        delivering = [(i, (1, 8 - i - 1)) for i in range(MAX_APPROACH_SLOTS + 1)]
        far_id = MAX_APPROACH_SLOTS
        far_pos = delivering[far_id][1]
        target, should_wait = gs.get_dropoff_approach_target(far_id, far_pos, drop_off, delivering)
        assert should_wait is True
        assert target != drop_off

    def test_already_at_dropoff_goes_directly(self):
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        # Only bot delivering -- should go directly
        delivering = [(0, (1, 7))]
        target, should_wait = gs.get_dropoff_approach_target(0, (1, 7), drop_off, delivering)
        assert target == drop_off
        assert should_wait is False

    def test_no_approach_cells_returns_dropoff(self):
        """When approach cells are empty, always returns dropoff."""
        gs = _make_gs_with_dropoff()
        gs.dropoff_approach_cells = []
        drop_off = (1, 8)
        target, should_wait = gs.get_dropoff_approach_target(0, (5, 5), drop_off, [(0, (5, 5))])
        assert target == drop_off
        assert should_wait is False

    def test_tiebreak_by_bot_id(self):
        """When two bots are equidistant, lower bot_id gets priority."""
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        # Both bots at same distance from dropoff
        delivering = [(0, (1, 6)), (1, (1, 6)), (2, (1, 6))]
        # Bot 0 and 1 should go directly (MAX_APPROACH_SLOTS=2)
        _, wait_0 = gs.get_dropoff_approach_target(0, (1, 6), drop_off, delivering)
        _, wait_1 = gs.get_dropoff_approach_target(1, (1, 6), drop_off, delivering)
        _, wait_2 = gs.get_dropoff_approach_target(2, (1, 6), drop_off, delivering)
        assert wait_0 is False
        assert wait_1 is False
        assert wait_2 is True


class TestIsDropoffCongested:
    def test_not_congested_with_few_bots(self):
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        # One bot near dropoff -- should not be congested
        assert gs.is_dropoff_congested(drop_off, [(1, 7)]) is False

    def test_congested_with_many_bots(self):
        from grocery_bot.game_state import MAX_APPROACH_SLOTS
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        # Place more bots than MAX_APPROACH_SLOTS near dropoff
        near_positions = gs.dropoff_approach_cells[:MAX_APPROACH_SLOTS + 1]
        if len(near_positions) > MAX_APPROACH_SLOTS:
            assert gs.is_dropoff_congested(drop_off, near_positions) is True

    def test_bots_far_away_not_congested(self):
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        far_bots = [(5, 1), (7, 1), (9, 1), (3, 1)]
        assert gs.is_dropoff_congested(drop_off, far_bots) is False

    def test_bot_on_dropoff_counts(self):
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        from grocery_bot.game_state import MAX_APPROACH_SLOTS
        # Place bots on dropoff itself plus approach cells
        positions = [drop_off] + gs.dropoff_approach_cells[:MAX_APPROACH_SLOTS]
        assert gs.is_dropoff_congested(drop_off, positions) is True


class TestGetAvoidanceTarget:
    def test_already_far_returns_none(self):
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        # Bot far from dropoff
        result = gs.get_avoidance_target((9, 1), drop_off)
        assert result is None

    def test_near_dropoff_returns_position(self):
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        # Bot right next to dropoff
        result = gs.get_avoidance_target((1, 7), drop_off)
        if result is not None:
            from grocery_bot.game_state import DROPOFF_CONGESTION_RADIUS
            d = gs.dist_static(result, drop_off)
            assert d > DROPOFF_CONGESTION_RADIUS

    def test_avoidance_target_is_walkable(self):
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        result = gs.get_avoidance_target((1, 7), drop_off)
        if result is not None:
            assert result not in gs.blocked_static

    def test_on_dropoff_gets_avoidance(self):
        """Bot standing on dropoff cell should get an avoidance target."""
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        # dist_static(drop_off, drop_off) == 0, which is <= CONGESTION_RADIUS
        result = gs.get_avoidance_target(drop_off, drop_off)
        # Should suggest moving away (if idle spots or wait cells exist)
        if gs.idle_spots or gs.dropoff_wait_cells:
            assert result is not None


class TestUpdateRoundPositions:
    def test_stores_positions(self):
        gs = _make_gs_with_dropoff()
        gs.update_round_positions({0: (1, 1), 1: (5, 5)}, (1, 8))
        assert gs._round_bot_positions == {0: (1, 1), 1: (5, 5)}
        assert gs._round_drop_off == (1, 8)

    def test_clears_targets(self):
        gs = _make_gs_with_dropoff()
        gs._round_bot_targets = {0: (1, 8)}
        gs.update_round_positions({0: (1, 1)}, (1, 8))
        assert gs._round_bot_targets == {}


class TestCountBotsNearDropoff:
    def test_no_bots_returns_zero(self):
        gs = _make_gs_with_dropoff()
        gs.update_round_positions({}, (1, 8))
        assert gs.count_bots_near_dropoff() == 0

    def test_counts_bots_in_approach_zone(self):
        gs = _make_gs_with_dropoff()
        # Place a bot on an approach cell
        if gs.dropoff_approach_cells:
            near_cell = gs.dropoff_approach_cells[0]
            gs.update_round_positions({0: near_cell, 1: (9, 1)}, (1, 8))
            assert gs.count_bots_near_dropoff() >= 1

    def test_excludes_specified_bot(self):
        gs = _make_gs_with_dropoff()
        if gs.dropoff_approach_cells:
            near_cell = gs.dropoff_approach_cells[0]
            gs.update_round_positions({0: near_cell}, (1, 8))
            assert gs.count_bots_near_dropoff(exclude_bot=0) == 0
            assert gs.count_bots_near_dropoff(exclude_bot=1) == 1

    def test_no_zones_returns_zero(self):
        gs = make_gs_with_state()  # no dropoff -> no zones
        gs.update_round_positions({0: (1, 7)}, (1, 8))
        assert gs.count_bots_near_dropoff() == 0


class TestCountBotsTargetingDropoff:
    def test_no_targets_returns_zero(self):
        gs = _make_gs_with_dropoff()
        gs.update_round_positions({0: (1, 1)}, (1, 8))
        assert gs.count_bots_targeting_dropoff() == 0

    def test_counts_bots_targeting(self):
        gs = _make_gs_with_dropoff()
        gs.update_round_positions({0: (1, 1), 1: (5, 5)}, (1, 8))
        gs.notify_bot_target(0, (1, 8))
        gs.notify_bot_target(1, (3, 3))
        assert gs.count_bots_targeting_dropoff() == 1

    def test_excludes_specified_bot(self):
        gs = _make_gs_with_dropoff()
        gs.update_round_positions({0: (1, 1), 1: (5, 5)}, (1, 8))
        gs.notify_bot_target(0, (1, 8))
        gs.notify_bot_target(1, (1, 8))
        assert gs.count_bots_targeting_dropoff(exclude_bot=0) == 1
        assert gs.count_bots_targeting_dropoff(exclude_bot=1) == 1
        assert gs.count_bots_targeting_dropoff() == 2

    def test_no_round_dropoff_returns_zero(self):
        gs = _make_gs_with_dropoff()
        # Don't call update_round_positions -> _round_drop_off is None
        gs._round_drop_off = None
        gs.notify_bot_target(0, (1, 8))
        assert gs.count_bots_targeting_dropoff() == 0


class TestNotifyBotTarget:
    def test_records_target(self):
        gs = _make_gs_with_dropoff()
        gs.notify_bot_target(0, (3, 3))
        assert gs._round_bot_targets[0] == (3, 3)

    def test_none_target(self):
        gs = _make_gs_with_dropoff()
        gs.notify_bot_target(0, None)
        assert gs._round_bot_targets[0] is None
