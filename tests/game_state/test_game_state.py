"""Tests for GameState: TSP, distance cache, multi-trip planning."""

import bot
from tests.conftest import make_state, reset_bot


class TestMultiTripPlanning:
    """For 4-item orders, the bot must make 2 trips. Multi-trip planning
    should evaluate all possible splits to minimize total rounds."""

    def test_plan_multi_trip_finds_optimal_split(self):
        """Directly test plan_multi_trip: leave close-to-dropoff item for trip 2."""
        reset_bot()
        # Set up blocked set with these items as shelves
        state = make_state(
            items=[
                {"id": "item_0", "type": "bread", "position": [2, 6]},
                {"id": "item_1", "type": "cheese", "position": [2, 3]},
                {"id": "item_2", "type": "milk", "position": [2, 2]},
                {"id": "item_3", "type": "yogurt", "position": [9, 3]},
            ],
            width=12,
            height=10,
        )
        bot.init_static(state)

        drop_off = (1, 8)
        # Bot NOT at dropoff — at (5, 5). This makes trips asymmetric.
        bot_pos = (5, 5)
        # adj cells: bread->(1,6)or(3,6), cheese->(1,3)or(3,3),
        #            milk->(1,2)or(3,2), yogurt->(8,3)or(10,3)
        items = state["items"]
        candidates = []
        for it in items:
            cell, _d = bot.find_best_item_target(bot_pos, it, bot._gs.blocked_static)
            if cell:
                candidates.append((it, cell))

        route = bot.plan_multi_trip(bot_pos, candidates, drop_off, capacity=3)
        # Route should be trip 1 items (up to 3).
        # The function minimizes total cost of trip1 + trip2.
        assert len(route) <= 3
        assert len(route) >= 1
        trip1_types = {it["type"] for it, _ in route}
        # Whatever split, total cost should be <= naive 3-closest approach
        trip1_cost = bot.tsp_cost(bot_pos, route, drop_off)
        trip2_items = [(it, cell) for it, cell in candidates if it["type"] not in trip1_types]
        trip2_cost = bot.tsp_cost(drop_off, trip2_items, drop_off) if trip2_items else 0
        total_optimal = trip1_cost + trip2_cost

        # Compare with greedy: 3 closest
        candidates_sorted = sorted(candidates, key=lambda c: bot.dist_static(bot_pos, c[1]))
        greedy_trip1 = candidates_sorted[:3]
        greedy_trip2 = candidates_sorted[3:]
        greedy_route1 = bot.tsp_route(bot_pos, greedy_trip1, drop_off)
        greedy_cost = bot.tsp_cost(bot_pos, greedy_route1, drop_off)
        if greedy_trip2:
            greedy_route2 = bot.tsp_route(drop_off, greedy_trip2, drop_off)
            greedy_cost += bot.tsp_cost(drop_off, greedy_route2, drop_off)

        assert total_optimal <= greedy_cost, (
            f"Multi-trip ({total_optimal}) should be <= greedy ({greedy_cost})"
        )

