"""GameState — persistent map caches and cross-round tracking."""

from itertools import combinations, permutations

from pathfinding import bfs_all, find_adjacent_positions


class GameState:
    """Encapsulates all mutable game state and caches for a single game."""

    def __init__(self):
        self.blocked_static = None
        self.dist_cache = {}
        self.adj_cache = {}
        self.last_pickup = {}
        self.pickup_fail_count = {}
        self.blacklisted_items = set()

    def reset(self):
        self.__init__()

    def init_static(self, state):
        """Compute static blocked set and caches on round 0."""
        self.dist_cache = {}
        self.adj_cache = {}

        walls = {tuple(w) for w in state["grid"]["walls"]}
        width, height = state["grid"]["width"], state["grid"]["height"]
        item_positions = {tuple(it["position"]) for it in state["items"]}

        blocked = set(walls)
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

    def get_distances_from(self, source):
        if source not in self.dist_cache:
            self.dist_cache[source] = bfs_all(source, self.blocked_static)
        return self.dist_cache[source]

    def dist_static(self, a, b):
        if a == b:
            return 0
        return self.get_distances_from(a).get(b, float("inf"))

    def find_best_item_target(self, pos, item):
        """Find the closest adjacent cell to reach an item shelf."""
        ipos = tuple(item["position"])
        adj_cells = self.adj_cache.get(
            ipos, find_adjacent_positions(ipos[0], ipos[1], self.blocked_static)
        )
        if not adj_cells:
            return None, float("inf")
        best_cell = None
        best_d = float("inf")
        for ac in adj_cells:
            d = self.dist_static(pos, ac)
            if d < best_d:
                best_d = d
                best_cell = ac
        return best_cell, best_d

    def tsp_route(self, bot_pos, item_targets, drop_off):
        """Find optimal pickup order via brute-force TSP."""
        if len(item_targets) <= 1:
            return item_targets
        best_order = None
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

    def tsp_cost(self, bot_pos, item_targets, drop_off):
        cost = 0
        prev = bot_pos
        for _, cell in item_targets:
            cost += self.dist_static(prev, cell)
            prev = cell
        cost += self.dist_static(prev, drop_off)
        return cost

    def plan_multi_trip(self, bot_pos, all_candidates, drop_off, capacity=3):
        """Find optimal split into trip1/trip2 for large orders."""
        n = len(all_candidates)
        if n <= capacity:
            return self.tsp_route(bot_pos, all_candidates, drop_off)
        best_cost = float("inf")
        best_trip1 = None
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
