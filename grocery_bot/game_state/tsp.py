"""TSP routing and multi-trip planning for GameState."""

from itertools import combinations, permutations
from typing import Any

from grocery_bot.constants import MAX_INVENTORY
from grocery_bot.game_state._base import GameStateBase


class TspMixin(GameStateBase):
    """Mixin providing TSP route optimization and interleaved delivery planning."""

    def tsp_route(
        self,
        bot_pos: tuple[int, int],
        item_targets: list[tuple[Any, tuple[int, int]]],
        drop_off: tuple[int, int],
    ) -> list[tuple[Any, tuple[int, int]]]:
        """Find optimal pickup order via brute-force TSP."""
        if len(item_targets) <= 1:
            return item_targets
        best_order: tuple[int, ...] | None = None
        best_cost = float("inf")
        for perm in permutations(range(len(item_targets))):
            cost: float = 0
            prev = bot_pos
            for idx in perm:
                _, cell = item_targets[idx]
                cost += self.dist_static(prev, cell)
                if cost >= best_cost:
                    break
                prev = cell
            else:
                cost += self.dist_static(prev, drop_off)
                if cost < best_cost:
                    best_cost = cost
                    best_order = perm
        if best_order is None:
            return item_targets
        return [item_targets[i] for i in best_order]

    def tsp_cost(
        self,
        bot_pos: tuple[int, int],
        item_targets: list[tuple[Any, tuple[int, int]]],
        drop_off: tuple[int, int],
    ) -> float:
        cost: float = 0
        prev = bot_pos
        for _, cell in item_targets:
            cost += self.dist_static(prev, cell)
            prev = cell
        cost += self.dist_static(prev, drop_off)
        return cost

    def plan_multi_trip(
        self,
        bot_pos: tuple[int, int],
        all_candidates: list[tuple[Any, tuple[int, int]]],
        drop_off: tuple[int, int],
        capacity: int = MAX_INVENTORY,
    ) -> list[tuple[Any, tuple[int, int]]]:
        """Find optimal split into trip1/trip2 for large orders."""
        n = len(all_candidates)
        if n <= capacity:
            return self.tsp_route(bot_pos, all_candidates, drop_off)
        best_cost = float("inf")
        best_trip1: list[tuple[Any, tuple[int, int]]] | None = None
        for trip1_size in range(max(1, n - capacity), min(capacity, n) + 1):
            for trip1_indices in combinations(range(n), trip1_size):
                trip2_indices = tuple(i for i in range(n) if i not in trip1_indices)
                if len(trip2_indices) > capacity:
                    continue
                trip1 = [all_candidates[i] for i in trip1_indices]
                trip2 = [all_candidates[i] for i in trip2_indices]
                route1 = self.tsp_route(bot_pos, trip1, drop_off)
                cost1 = self.tsp_cost(bot_pos, route1, drop_off)
                route2 = self.tsp_route(drop_off, trip2, drop_off)
                cost2 = self.tsp_cost(drop_off, route2, drop_off)
                total = cost1 + cost2
                if total < best_cost:
                    best_cost = total
                    best_trip1 = route1
        return best_trip1 or self.tsp_route(bot_pos, all_candidates[:capacity], drop_off)

    def plan_interleaved_route(
        self,
        bot_pos: tuple[int, int],
        item_targets: list[tuple[Any, tuple[int, int]]],
        drop_off: tuple[int, int],
        capacity: int = MAX_INVENTORY,
    ) -> list[tuple[str, Any]]:
        """Compare full-pickup-then-deliver vs deliver-when-passing-dropoff.

        Returns list of (action_type, target) tuples:
        - ("pickup", (item, cell))
        - ("deliver", drop_off)
        """
        n = len(item_targets)
        if n == 0:
            return []
        if n == 1:
            return [("pickup", item_targets[0]), ("deliver", drop_off)]

        # Strategy 1: Full pickup then deliver
        if n <= capacity:
            full_route = self.tsp_route(bot_pos, item_targets, drop_off)
            full_cost = self.tsp_cost(bot_pos, full_route, drop_off)
            best_cost = full_cost
            best_plan: list[tuple[str, Any]] | None = [("pickup", it) for it in full_route] + [
                ("deliver", drop_off)
            ]
        else:
            best_cost = float("inf")
            best_plan = None

        # Strategy 2: Interleaved — split into two batches
        if n > capacity:
            min_b1 = max(1, n - capacity)
            max_b1 = min(capacity, n - 1)
        else:
            min_b1 = 1
            max_b1 = n - 1

        for b1_size in range(min_b1, max_b1 + 1):
            if n - b1_size > capacity:
                continue
            for b1_indices in combinations(range(n), b1_size):
                batch1 = [item_targets[i] for i in b1_indices]
                batch2 = [item_targets[i] for i in range(n) if i not in b1_indices]

                route1 = self.tsp_route(bot_pos, batch1, drop_off)
                cost1 = self.tsp_cost(bot_pos, route1, drop_off)
                route2 = self.tsp_route(drop_off, batch2, drop_off)
                cost2 = self.tsp_cost(drop_off, route2, drop_off)

                total = cost1 + cost2
                if total < best_cost:
                    best_cost = total
                    best_plan = (
                        [("pickup", it) for it in route1]
                        + [("deliver", drop_off)]
                        + [("pickup", it) for it in route2]
                        + [("deliver", drop_off)]
                    )

        return best_plan or []
