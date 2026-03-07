"""Pickup logic (active items, routing) for RoundPlanner."""

from itertools import permutations
from typing import Any, Optional

from grocery_bot.pathfinding import DIRECTIONS
from grocery_bot.constants import (
    CLUSTER_DISTANCE_WEIGHT,
    MAX_INVENTORY,
    PREDICTION_TEAM_MIN,
)

# Teams >= this size skip best_pickup in greedy routing to avoid convergence.
MEDIUM_TEAM_MIN_PICKUP = PREDICTION_TEAM_MIN


class PickupMixin:
    """Mixin providing active item pickup, preview pre-pick, and route building."""

    def _try_active_pickup(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        inv: list[str],
        blocked: set[tuple[int, int]],
    ) -> bool:
        """Pick up adjacent active items, or navigate via TSP route."""
        # Adjacent pickup via position lookup (zero cost - always take it)
        if len(inv) < MAX_INVENTORY:
            for dx, dy in DIRECTIONS:
                for it in self.items_at_pos.get((bx + dx, by + dy), []):
                    if not self._is_available(it):
                        continue
                    if self.net_active.get(it["type"], 0) <= 0:
                        continue
                    self._claim(it, self.net_active)
                    self._emit(bid, bx, by, self._pickup(bid, it))
                    return True

        if len(inv) >= MAX_INVENTORY:
            return False

        # Pre-assigned route (multi-bot optimization)
        if bid in self.bot_assignments:
            route = self._build_assigned_route(bid, pos)
            if route:
                for it, _ in route:
                    self._claim(it, self.net_active)
                if self._emit_move(bid, bx, by, pos, route[0][1], blocked):
                    return True
                # Try alternative adjacent cells if first target blocked
                first_item = route[0][0]
                ipos = tuple(first_item["position"])
                for ac in self.gs.adj_cache.get(ipos, []):
                    if ac != route[0][1] and ac not in blocked:
                        if self._emit_move(bid, bx, by, pos, ac, blocked):
                            return True

        # Greedy fallback: find reachable items and plan TSP route
        route = self._build_greedy_route(pos, inv)
        if route:
            for it, _ in route:
                self._claim(it, self.net_active)
            if self._emit_move(bid, bx, by, pos, route[0][1], blocked):
                return True
            # First target blocked by another bot — try alternative adjacent cells
            first_item = route[0][0]
            ipos = tuple(first_item["position"])
            for ac in self.gs.adj_cache.get(ipos, []):
                if ac != route[0][1] and ac not in blocked:
                    if self._emit_move(bid, bx, by, pos, ac, blocked):
                        return True

        return False

    def _build_assigned_route(
        self, bid: int, pos: tuple[int, int]
    ) -> Optional[list[tuple[Any, tuple[int, int]]]]:
        assigned: list[tuple[Any, tuple[int, int]]] = []
        for it in self.bot_assignments[bid]:
            if it["id"] in self.claimed:
                continue
            cell, d = self.gs.find_best_item_target(pos, it)
            if cell and d < float("inf"):
                assigned.append((it, cell))
        if assigned:
            return self.gs.tsp_route(pos, assigned, self.drop_off)
        return None

    def _build_greedy_route(
        self, pos: tuple[int, int], inv: list[str]
    ) -> Optional[list[tuple[Any, tuple[int, int]]]]:
        # Single-bot: use optimized item selection
        if len(self.bots) <= 1:
            return self._build_single_bot_route(pos, inv)

        # For large teams (8+), best_pickup causes convergence on same cells.
        use_best_pickup = len(self.bots) < MEDIUM_TEAM_MIN_PICKUP and self.gs.best_pickup

        candidates: list[tuple[Any, tuple[int, int], float]] = []
        for it, _ in self._iter_needed_items(self.net_active):
            t = it["type"]
            if use_best_pickup and t in self.gs.best_pickup:
                cell, _ipos, d_drop = self.gs.best_pickup[t]
                d = self.gs.dist_static(pos, cell)
            else:
                cell, d = self.gs.find_best_item_target(pos, it)
                if not cell or d == float("inf"):
                    continue
                d_drop = self.gs.dist_static(cell, self.drop_off)
            round_trip = d + 1 + d_drop
            if round_trip < self.rounds_left:
                score = d + d_drop
                candidates.append((it, cell, score))

        if not candidates:
            return None

        # Phase 4.2: Item proximity clustering
        if len(candidates) > 1:
            candidates = self._cluster_select(candidates)

        slots = min(MAX_INVENTORY - len(inv), self.max_claim)

        selected: list[tuple[Any, tuple[int, int]]] = []
        selected_types: dict[str, int] = {}
        for it, cell, d in candidates:
            t = it["type"]
            still_needed = self.net_active.get(t, 0) - selected_types.get(t, 0)
            if still_needed > 0:
                selected.append((it, cell))
                selected_types[t] = selected_types.get(t, 0) + 1

        if not selected:
            return None
        if len(selected) > slots:
            return self.gs.plan_multi_trip(pos, selected, self.drop_off, slots)
        return self.gs.tsp_route(pos, selected, self.drop_off)

    def _build_single_bot_route(
        self, pos: tuple[int, int], inv: list[str]
    ) -> Optional[list[tuple[Any, tuple[int, int]]]]:
        """Optimized route for single bot: use precomputed route tables."""
        slots = MAX_INVENTORY - len(inv)
        if slots <= 0:
            return None

        # Collect needed types with available items
        needed_types: list[str] = []
        type_to_item: dict[str, Any] = {}
        for it, _ in self._iter_needed_items(self.net_active):
            t = it["type"]
            if t not in type_to_item:
                type_to_item[t] = it
                needed_types.append(t)

        if not needed_types:
            return None

        # Try precomputed optimal route (deterministic, no per-round recomputation)
        route_types = needed_types[:slots]
        optimal = self.gs.get_optimal_route(route_types, pos, self.drop_off)
        if optimal:
            # Map (type, cell) -> (item, cell), verify reachability
            selected: list[tuple[Any, tuple[int, int]]] = []
            for t, cell in optimal:
                it = type_to_item.get(t)
                if it is None:
                    continue
                d_bot = self.gs.dist_static(pos, cell)
                d_drop = self.gs.dist_static(cell, self.drop_off)
                if d_bot + 1 + d_drop < self.rounds_left:
                    selected.append((it, cell))
            if selected:
                return selected

        # Fallback: manual computation if precomputed route unavailable
        candidates: list[tuple[Any, tuple[int, int], float]] = []
        for t in needed_types:
            if t in self.gs.best_pickup:
                cell, _ipos, d_drop = self.gs.best_pickup[t]
                it = type_to_item[t]
                d_bot = self.gs.dist_static(pos, cell)
                if d_bot + 1 + d_drop < self.rounds_left:
                    candidates.append((it, cell, d_bot + d_drop))
            else:
                it = type_to_item[t]
                cell, d = self.gs.find_best_item_target(pos, it)
                if cell and d < float("inf"):
                    d_drop = self.gs.dist_static(cell, self.drop_off)
                    if d + 1 + d_drop < self.rounds_left:
                        candidates.append((it, cell, d + d_drop))

        if not candidates:
            return None

        candidates.sort(key=lambda c: c[2])
        selected = [(it, cell) for it, cell, _ in candidates[:slots]]
        if not selected:
            return None
        return self._flexible_tsp(pos, selected, self.drop_off)

    def _flexible_tsp(
        self,
        bot_pos: tuple[int, int],
        item_targets: list[tuple[Any, tuple[int, int]]],
        drop_off: tuple[int, int],
    ) -> list[tuple[Any, tuple[int, int]]]:
        """TSP that considers ALL adjacent cells per item for better routes."""
        n = len(item_targets)
        if n <= 1:
            if n == 1:
                it, _ = item_targets[0]
                ipos = tuple(it["position"])
                best_cell: Optional[tuple[int, int]] = None
                best_cost = float("inf")
                for ac in self.gs.adj_cache.get(ipos, []):
                    cost = self.gs.dist_static(bot_pos, ac) + self.gs.dist_static(
                        ac, drop_off
                    )
                    if cost < best_cost:
                        best_cost = cost
                        best_cell = ac
                if best_cell:
                    return [(it, best_cell)]
            return item_targets

        item_cells: list[tuple[Any, list[tuple[int, int]]]] = []
        for it, default_cell in item_targets:
            ipos = tuple(it["position"])
            cells = self.gs.adj_cache.get(ipos, [default_cell])
            if not cells:
                cells = [default_cell]
            item_cells.append((it, cells))

        best_order: Optional[list[tuple[int, tuple[int, int]]]] = None
        best_cost = float("inf")

        for perm in permutations(range(n)):
            cost: float = 0
            prev = bot_pos
            cells_chosen: list[tuple[int, tuple[int, int]]] = []
            for idx in perm:
                it, cells = item_cells[idx]
                bc = min(cells, key=lambda c: self.gs.dist_static(prev, c))
                d = self.gs.dist_static(prev, bc)
                cost += d
                if cost >= best_cost:
                    break
                prev = bc
                cells_chosen.append((idx, bc))
            else:
                cost += self.gs.dist_static(prev, drop_off)
                if cost < best_cost:
                    best_cost = cost
                    best_order = cells_chosen

        if best_order is None:
            return item_targets

        return [(item_cells[idx][0], cell) for idx, cell in best_order]

    def _cluster_select(
        self, candidates: list[tuple[Any, tuple[int, int], float]]
    ) -> list[tuple[Any, tuple[int, int], float]]:
        """For same-type items, prefer the one closest to other needed items."""
        all_positions = [cell for _, cell, _ in candidates]
        if len(all_positions) < 2:
            return candidates
        cx = sum(p[0] for p in all_positions) / len(all_positions)
        cy = sum(p[1] for p in all_positions) / len(all_positions)

        by_type: dict[str, list[tuple[Any, tuple[int, int], float]]] = {}
        for entry in candidates:
            t = entry[0]["type"]
            by_type.setdefault(t, []).append(entry)

        result: list[tuple[Any, tuple[int, int], float]] = []
        for t, entries in by_type.items():
            needed = self.net_active.get(t, 0)
            if len(entries) <= needed:
                entries.sort(key=lambda e: e[2])
                result.extend(entries)
            else:
                scored: list[tuple[Any, tuple[int, int], float, float]] = []
                for entry in entries:
                    _, cell, d = entry
                    cluster_d = abs(cell[0] - cx) + abs(cell[1] - cy)
                    scored.append((*entry, d + CLUSTER_DISTANCE_WEIGHT * cluster_d))
                scored.sort(key=lambda e: e[3])
                result.extend((it, cell, d) for it, cell, d, _ in scored)

        result.sort(key=lambda c: c[2])
        return result

