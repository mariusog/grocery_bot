"""GameState — persistent map caches, cross-round tracking, and algorithms."""

from itertools import combinations, permutations
from typing import Any, Optional

from pathfinding import bfs_all, find_adjacent_positions
from constants import (
    CORRIDOR_HEIGHT_THRESHOLD,
    HUNGARIAN_MAX_PAIRS,
    LAST_ITEM_BOOST_THRESHOLD,
    LAST_ITEM_COST_MULTIPLIER,
    MAX_INVENTORY,
    ZONE_CROSS_PENALTY,
)


class GameState:
    """Encapsulates all mutable game state and caches for a single game."""

    def __init__(self) -> None:
        self.blocked_static: Optional[set[tuple[int, int]]] = None
        self.dist_cache: dict[tuple[int, int], dict[tuple[int, int], int]] = {}
        self.adj_cache: dict[tuple[int, int], list[tuple[int, int]]] = {}
        self.last_pickup: dict[int, tuple[str, int]] = {}
        self.pickup_fail_count: dict[str, int] = {}
        self.blacklisted_items: set[str] = set()
        self.corridor_y: list[int] = []
        self.idle_spots: list[tuple[int, int]] = []
        self.grid_width: int = 0
        self.grid_height: int = 0

        # Precomputed route tables (populated in init_static)
        self.best_pickup: dict[
            str, tuple[tuple[int, int], tuple[int, int], float]
        ] = {}
        self.best_pair_route: dict[
            tuple[str, str], list[tuple[str, tuple[int, int]]]
        ] = {}
        self.best_triple_route: dict[
            tuple[str, str, str], list[tuple[str, tuple[int, int]]]
        ] = {}

        # Current active items remaining on shelves (set by RoundPlanner)
        self.active_on_shelves: int = 0

        # --- Persistent coordination state (T15) ---
        # Delivery queue: ordered list of bot IDs waiting to deliver
        self.delivery_queue: list[int] = []
        # Persistent task assignments: bot_id -> task dict
        self.bot_tasks: dict[int, dict[str, Any]] = {}
        # Track the active order ID to detect order transitions
        self.last_active_order_id: Optional[str] = None

    def reset(self) -> None:
        self.blocked_static = None
        self.dist_cache = {}
        self.adj_cache = {}
        self.last_pickup = {}
        self.pickup_fail_count = {}
        self.blacklisted_items = set()
        self.corridor_y = []
        self.idle_spots = []
        self.grid_width = 0
        self.grid_height = 0
        self.best_pickup = {}
        self.best_pair_route = {}
        self.best_triple_route = {}
        self.active_on_shelves = 0
        self.delivery_queue = []
        self.bot_tasks = {}
        self.last_active_order_id = None

    def init_static(self, state: dict[str, Any]) -> None:
        """Compute static blocked set and caches on round 0."""
        self.dist_cache = {}
        self.adj_cache = {}

        walls = {tuple(w) for w in state["grid"]["walls"]}
        width: int = state["grid"]["width"]
        height: int = state["grid"]["height"]
        self.grid_width = width
        self.grid_height = height
        item_positions = {tuple(it["position"]) for it in state["items"]}

        blocked: set[tuple[int, int]] = set(walls)
        for x in range(-1, width + 1):
            blocked.add((x, -1))
            blocked.add((x, height))
        for y in range(-1, height + 1):
            blocked.add((-1, y))
            blocked.add((width, y))
        blocked |= item_positions
        self.blocked_static = blocked

        for it in state["items"]:
            ipos = tuple(it["position"])
            self.adj_cache[ipos] = find_adjacent_positions(
                ipos[0], ipos[1], self.blocked_static
            )

        self._compute_idle_spots(width, height, item_positions)

        # Precompute route tables if drop_off is available
        if "drop_off" in state:
            drop_off = tuple(state["drop_off"])
            self._precompute_route_tables(state["items"], drop_off)

    def _precompute_route_tables(
        self,
        items: list[dict[str, Any]],
        drop_off: tuple[int, int],
    ) -> None:
        """Precompute optimal pickup cells and multi-item routes per type."""
        # Group items by type
        items_by_type: dict[str, list[dict[str, Any]]] = {}
        for it in items:
            items_by_type.setdefault(it["type"], []).append(it)

        # (a) Best pickup cell per item type: minimize dist(adj_cell, dropoff)
        self.best_pickup = {}
        for item_type, type_items in items_by_type.items():
            best_cell: Optional[tuple[int, int]] = None
            best_ipos: Optional[tuple[int, int]] = None
            best_d: float = float("inf")
            for it in type_items:
                ipos = tuple(it["position"])
                for ac in self.adj_cache.get(ipos, []):
                    d = self.dist_static(ac, drop_off)
                    if d < best_d:
                        best_d = d
                        best_cell = ac
                        best_ipos = ipos
            if best_cell is not None and best_ipos is not None:
                self.best_pickup[item_type] = (best_cell, best_ipos, best_d)

        # (b) Best 2-type pickup routes
        all_types = sorted(self.best_pickup.keys())
        self.best_pair_route = {}
        for t1, t2 in combinations(all_types, 2):
            cell1 = self.best_pickup[t1][0]
            cell2 = self.best_pickup[t2][0]
            # Order 1: dropoff -> t1 -> t2 -> dropoff
            cost_12 = (
                self.dist_static(drop_off, cell1)
                + self.dist_static(cell1, cell2)
                + self.dist_static(cell2, drop_off)
            )
            # Order 2: dropoff -> t2 -> t1 -> dropoff
            cost_21 = (
                self.dist_static(drop_off, cell2)
                + self.dist_static(cell2, cell1)
                + self.dist_static(cell1, drop_off)
            )
            if cost_12 <= cost_21:
                self.best_pair_route[(t1, t2)] = [
                    (t1, cell1), (t2, cell2)
                ]
            else:
                self.best_pair_route[(t1, t2)] = [
                    (t2, cell2), (t1, cell1)
                ]

        # (c) Best 3-type pickup routes
        self.best_triple_route = {}
        for types in combinations(all_types, 3):
            cells = [self.best_pickup[t][0] for t in types]
            best_perm: Optional[tuple[int, ...]] = None
            best_cost: float = float("inf")
            for perm in permutations(range(3)):
                cost: float = self.dist_static(drop_off, cells[perm[0]])
                prev = cells[perm[0]]
                for i in range(1, 3):
                    cost += self.dist_static(prev, cells[perm[i]])
                    if cost >= best_cost:
                        break
                    prev = cells[perm[i]]
                else:
                    cost += self.dist_static(prev, drop_off)
                    if cost < best_cost:
                        best_cost = cost
                        best_perm = perm
            if best_perm is not None:
                key = tuple(sorted(types))
                self.best_triple_route[key] = [
                    (types[i], cells[i]) for i in best_perm
                ]

    def get_optimal_route(
        self,
        item_types: list[str],
        bot_pos: tuple[int, int],
        drop_off: tuple[int, int],
    ) -> Optional[list[tuple[str, tuple[int, int]]]]:
        """Return precomputed optimal route for given item types.

        Adjusts for bot position — the precomputed route assumes starting
        from dropoff, but if the bot is closer to a different first stop,
        we may reverse or re-order.

        Returns None if no precomputed route is available.
        """
        n = len(item_types)
        if n == 0:
            return None

        if n == 1:
            t = item_types[0]
            if t in self.best_pickup:
                cell, _ipos, _d = self.best_pickup[t]
                return [(t, cell)]
            return None

        if n == 2:
            key = tuple(sorted(item_types))
            route = self.best_pair_route.get(key)
            if route is None:
                return None
            # Check if bot position favors reverse order
            cost_fwd = self.dist_static(bot_pos, route[0][1])
            cost_rev = self.dist_static(bot_pos, route[-1][1])
            if cost_rev < cost_fwd:
                # Recompute: bot -> last -> first -> dropoff vs bot -> first -> last -> dropoff
                rev = list(reversed(route))
                cost_fwd_total = (
                    cost_fwd
                    + self.dist_static(route[0][1], route[1][1])
                    + self.dist_static(route[1][1], drop_off)
                )
                cost_rev_total = (
                    cost_rev
                    + self.dist_static(rev[0][1], rev[1][1])
                    + self.dist_static(rev[1][1], drop_off)
                )
                if cost_rev_total < cost_fwd_total:
                    return rev
            return list(route)

        if n == 3:
            key = tuple(sorted(item_types))
            route = self.best_triple_route.get(key)
            if route is None:
                return None
            # Try all 6 permutations starting from bot_pos
            cells = [(t, c) for t, c in route]
            best_order: Optional[list[tuple[str, tuple[int, int]]]] = None
            best_cost: float = float("inf")
            for perm in permutations(range(3)):
                cost = self.dist_static(bot_pos, cells[perm[0]][1])
                prev = cells[perm[0]][1]
                for i in range(1, 3):
                    cost += self.dist_static(prev, cells[perm[i]][1])
                    if cost >= best_cost:
                        break
                    prev = cells[perm[i]][1]
                else:
                    cost += self.dist_static(prev, drop_off)
                    if cost < best_cost:
                        best_cost = cost
                        best_order = [cells[j] for j in perm]
            return best_order

        return None

    def _compute_idle_spots(
        self, width: int, height: int, item_positions: set[tuple[int, int]]
    ) -> None:
        """Precompute strategic idle positions along the middle corridor.

        Idle spots are walkable cells at the walkway columns (between shelf
        pairs) on the middle corridor row(s). Bots at these positions can
        quickly enter any aisle to pick items.
        """
        # Find middle corridor rows
        mid = height // 2
        corridor_rows = [mid]
        if height > CORRIDOR_HEIGHT_THRESHOLD:
            corridor_rows.append(mid - 1)
        self.corridor_y = [y for y in corridor_rows if 1 <= y < height - 1]

        # Find walkway columns (columns between shelf pairs)
        shelf_xs: set[int] = {pos[0] for pos in item_positions}
        walkway_xs: set[int] = set()
        for sx in shelf_xs:
            for dx in [-1, 1]:
                ax = sx + dx
                if 0 < ax < width - 1 and ax not in shelf_xs:
                    walkway_xs.add(ax)

        # Generate idle spots at corridor + walkway intersections
        self.idle_spots = []
        for cy in self.corridor_y:
            for wx in sorted(walkway_xs):
                pos = (wx, cy)
                if pos not in self.blocked_static:
                    self.idle_spots.append(pos)

        # Overflow spots: one row above/below corridor
        for cy in self.corridor_y:
            for dy in [-1, 1]:
                ny = cy + dy
                if ny < 1 or ny >= height - 1:
                    continue
                for wx in sorted(walkway_xs):
                    pos = (wx, ny)
                    if pos not in self.blocked_static:
                        self.idle_spots.append(pos)

    def get_distances_from(
        self, source: tuple[int, int]
    ) -> dict[tuple[int, int], int]:
        if source not in self.dist_cache:
            self.dist_cache[source] = bfs_all(source, self.blocked_static)
        return self.dist_cache[source]

    def dist_static(self, a: tuple[int, int], b: tuple[int, int]) -> float:
        if a == b:
            return 0
        return self.get_distances_from(a).get(b, float("inf"))

    def find_best_item_target(
        self, pos: tuple[int, int], item: dict[str, Any]
    ) -> tuple[Optional[tuple[int, int]], float]:
        """Find the closest adjacent cell to reach an item shelf."""
        ipos = tuple(item["position"])
        adj_cells = self.adj_cache.get(
            ipos, find_adjacent_positions(ipos[0], ipos[1], self.blocked_static)
        )
        if not adj_cells:
            return None, float("inf")
        best_cell: Optional[tuple[int, int]] = None
        best_d = float("inf")
        for ac in adj_cells:
            d = self.dist_static(pos, ac)
            if d < best_d:
                best_d = d
                best_cell = ac
        return best_cell, best_d

    def tsp_route(
        self,
        bot_pos: tuple[int, int],
        item_targets: list[tuple[Any, tuple[int, int]]],
        drop_off: tuple[int, int],
    ) -> list[tuple[Any, tuple[int, int]]]:
        """Find optimal pickup order via brute-force TSP."""
        if len(item_targets) <= 1:
            return item_targets
        best_order: Optional[tuple[int, ...]] = None
        best_cost = float("inf")
        for perm in permutations(range(len(item_targets))):
            cost = 0
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
        best_trip1: Optional[list[tuple[Any, tuple[int, int]]]] = None
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

    # ------------------------------------------------------------------
    # Phase 1.3: Interleaved Pickup-Delivery
    # ------------------------------------------------------------------

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
            best_plan: Optional[list[tuple[str, Any]]] = (
                [("pickup", it) for it in full_route] + [("deliver", drop_off)]
            )
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

    # ------------------------------------------------------------------
    # Phase 3.1: Hungarian Algorithm
    # ------------------------------------------------------------------

    def assign_items_to_bots(
        self,
        assignable_bots: list[tuple[int, tuple[int, int], int]],
        candidate_items: list[dict[str, Any]],
        zone_width: Optional[float] = None,
    ) -> dict[int, list[dict[str, Any]]]:
        """Assign items to bots optimally using Hungarian algorithm.

        Args:
            assignable_bots: list of (bot_id, bot_pos, slots) tuples.
            candidate_items: list of item dicts with "position" key.
            zone_width: if set, add zone penalty for cross-zone assignments.

        Returns:
            dict mapping bot_id -> list of assigned item dicts.
        """
        if not assignable_bots or not candidate_items:
            return {}

        # Last-item priority boost: when 1-2 active items remain, reduce
        # their cost by 3x so the closest bot is strongly assigned to them.
        # Uses candidate count as proxy for active items on shelves.
        priority_multiplier: float = 1.0
        n_candidates = len(candidate_items)
        if 0 < n_candidates <= LAST_ITEM_BOOST_THRESHOLD and len(assignable_bots) > 1:
            priority_multiplier = LAST_ITEM_COST_MULTIPLIER

        # Build cost matrix: rows=bots, cols=items
        cost_matrix: list[list[float]] = []
        for bi, (_, bot_pos, _) in enumerate(assignable_bots):
            row: list[float] = []
            bot_zone = int(bot_pos[0] / zone_width) if zone_width else 0
            for ii, it in enumerate(candidate_items):
                _, d = self.find_best_item_target(bot_pos, it)
                if zone_width:
                    item_zone = int(it["position"][0] / zone_width)
                    d += abs(bot_zone - item_zone) * ZONE_CROSS_PENALTY
                d *= priority_multiplier
                row.append(d)
            cost_matrix.append(row)

        # Use Hungarian for small matrices, greedy for large
        n_bots = len(assignable_bots)
        n_items = len(candidate_items)
        if n_bots * n_items <= HUNGARIAN_MAX_PAIRS:
            pairs = _hungarian_solve(cost_matrix)
        else:
            pairs = []
            flat: list[tuple[float, int, int]] = []
            for i, row in enumerate(cost_matrix):
                for j, d in enumerate(row):
                    if d < float("inf"):
                        flat.append((d, i, j))
            flat.sort()
            used_b: set[int] = set()
            used_i: set[int] = set()
            for d, bi, ii in flat:
                if bi not in used_b and ii not in used_i:
                    pairs.append((bi, ii))
                    used_b.add(bi)
                    used_i.add(ii)

        # Convert pairs to bot_id -> items, respecting slot limits
        result: dict[int, list[dict[str, Any]]] = {}
        bot_counts: dict[int, int] = {}
        for bi, ii in sorted(pairs, key=lambda p: cost_matrix[p[0]][p[1]]):
            bot_id, _, slots = assignable_bots[bi]
            if bot_counts.get(bot_id, 0) >= slots:
                continue
            result.setdefault(bot_id, []).append(candidate_items[ii])
            bot_counts[bot_id] = bot_counts.get(bot_id, 0) + 1

        return result

    def hungarian_assign(
        self,
        bot_positions: list[tuple[int, int]],
        item_positions: list[tuple[int, int]],
        dist_fn: Optional[Any] = None,
    ) -> list[tuple[int, int]]:
        """Optimal bot-to-item assignment. Falls back to greedy for >100 pairs."""
        if not bot_positions or not item_positions:
            return []

        if dist_fn is None:
            dist_fn = self.dist_static

        n_bots = len(bot_positions)
        n_items = len(item_positions)

        if n_bots * n_items > HUNGARIAN_MAX_PAIRS:
            return _greedy_assign(bot_positions, item_positions, dist_fn)

        cost_matrix: list[list[float]] = []
        for i in range(n_bots):
            row: list[float] = []
            for j in range(n_items):
                row.append(dist_fn(bot_positions[i], item_positions[j]))
            cost_matrix.append(row)

        return _hungarian_solve(cost_matrix)


# ------------------------------------------------------------------
# Hungarian algorithm internals (module-level for reuse)
# ------------------------------------------------------------------

def _hungarian_solve(cost_matrix: list[list[float]]) -> list[tuple[int, int]]:
    """Solve assignment problem using Hungarian/Munkres algorithm O(n^3)."""
    if not cost_matrix or not cost_matrix[0]:
        return []

    n_rows = len(cost_matrix)
    n_cols = len(cost_matrix[0])
    n = max(n_rows, n_cols)
    INF = float("inf")

    has_finite = any(val < INF for row in cost_matrix for val in row)
    if not has_finite:
        return []

    max_finite = max(
        (val for row in cost_matrix for val in row if val < INF), default=0
    )
    pad_val = max_finite * n + 1

    matrix: list[list[float]] = []
    for i in range(n):
        row: list[float] = []
        for j in range(n):
            if i < n_rows and j < n_cols:
                val = cost_matrix[i][j]
                row.append(pad_val if val == INF else val)
            else:
                row.append(pad_val)
        matrix.append(row)

    u: list[float] = [0.0] * (n + 1)
    v: list[float] = [0.0] * (n + 1)
    p: list[int] = [0] * (n + 1)
    way: list[int] = [0] * (n + 1)

    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        min_v: list[float] = [INF] * (n + 1)
        used: list[bool] = [False] * (n + 1)

        while True:
            used[j0] = True
            i0 = p[j0]
            delta = INF
            j1 = -1

            for j in range(1, n + 1):
                if used[j]:
                    continue
                cur = matrix[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < min_v[j]:
                    min_v[j] = cur
                    way[j] = j0
                if min_v[j] < delta:
                    delta = min_v[j]
                    j1 = j

            if j1 == -1:
                break

            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    min_v[j] -= delta

            j0 = j1
            if p[j0] == 0:
                break

        while j0 != 0:
            p[j0] = p[way[j0]]
            j0 = way[j0]

    result: list[tuple[int, int]] = []
    for j in range(1, n + 1):
        row_idx = p[j] - 1
        col_idx = j - 1
        if row_idx < n_rows and col_idx < n_cols:
            if cost_matrix[row_idx][col_idx] < INF:
                result.append((row_idx, col_idx))
    return result


def _greedy_assign(
    bot_positions: list[tuple[int, int]],
    item_positions: list[tuple[int, int]],
    dist_fn: Any,
) -> list[tuple[int, int]]:
    """Greedy fallback for large inputs."""
    pairs: list[tuple[float, int, int]] = []
    for i, bp in enumerate(bot_positions):
        for j, ip in enumerate(item_positions):
            d = dist_fn(bp, ip)
            if d < float("inf"):
                pairs.append((d, i, j))
    pairs.sort()

    assigned_bots: set[int] = set()
    assigned_items: set[int] = set()
    result: list[tuple[int, int]] = []
    for d, bi, ii in pairs:
        if bi in assigned_bots or ii in assigned_items:
            continue
        result.append((bi, ii))
        assigned_bots.add(bi)
        assigned_items.add(ii)
        if len(result) >= min(len(bot_positions), len(item_positions)):
            break
    return result
