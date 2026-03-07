"""Unit tests for GameState methods (game_state.py)."""

from tests.conftest import make_gs_with_state


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
