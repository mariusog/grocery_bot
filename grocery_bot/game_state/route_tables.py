"""Precomputed route tables for optimal item pickup ordering."""

from itertools import combinations, permutations
from typing import Any

from grocery_bot.game_state._base import GameStateBase


class RouteTableMixin(GameStateBase):
    """Mixin providing precomputed pickup routes per item type."""

    def _precompute_route_tables(
        self,
        items: list[dict[str, Any]],
        drop_off: tuple[int, int],
    ) -> None:
        """Precompute optimal pickup cells and multi-item routes per type."""
        items_by_type: dict[str, list[dict[str, Any]]] = {}
        for it in items:
            items_by_type.setdefault(it["type"], []).append(it)

        # Best pickup cell per item type: minimize dist(adj_cell, dropoff)
        self.best_pickup = {}
        for item_type, type_items in items_by_type.items():
            best_cell: tuple[int, int] | None = None
            best_ipos: tuple[int, int] | None = None
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

        # Best 2-type pickup routes
        all_types = sorted(self.best_pickup.keys())
        self.best_pair_route = {}
        for t1, t2 in combinations(all_types, 2):
            cell1 = self.best_pickup[t1][0]
            cell2 = self.best_pickup[t2][0]
            cost_12 = (
                self.dist_static(drop_off, cell1)
                + self.dist_static(cell1, cell2)
                + self.dist_static(cell2, drop_off)
            )
            cost_21 = (
                self.dist_static(drop_off, cell2)
                + self.dist_static(cell2, cell1)
                + self.dist_static(cell1, drop_off)
            )
            if cost_12 <= cost_21:
                self.best_pair_route[(t1, t2)] = [(t1, cell1), (t2, cell2)]
            else:
                self.best_pair_route[(t1, t2)] = [(t2, cell2), (t1, cell1)]

        # Best 3-type pickup routes
        self.best_triple_route = {}
        for types in combinations(all_types, 3):
            cells = [self.best_pickup[t][0] for t in types]
            best_perm: tuple[int, ...] | None = None
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
                s = sorted(types)
                triple_key: tuple[str, str, str] = (s[0], s[1], s[2])
                self.best_triple_route[triple_key] = [(types[i], cells[i]) for i in best_perm]

    def get_optimal_route(
        self,
        item_types: list[str],
        bot_pos: tuple[int, int],
        drop_off: tuple[int, int],
    ) -> list[tuple[str, tuple[int, int]]] | None:
        """Return precomputed optimal route for given item types.

        Adjusts for bot position — the precomputed route assumes starting
        from dropoff, but if the bot is closer to a different first stop,
        we may reverse or re-order.
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
            s = sorted(item_types)
            key2: tuple[str, str] = (s[0], s[1])
            route = self.best_pair_route.get(key2)
            if route is None:
                return None
            cost_fwd = self.dist_static(bot_pos, route[0][1])
            cost_rev = self.dist_static(bot_pos, route[-1][1])
            if cost_rev < cost_fwd:
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
            s3 = sorted(item_types)
            key3: tuple[str, str, str] = (s3[0], s3[1], s3[2])
            route = self.best_triple_route.get(key3)
            if route is None:
                return None
            cells = [(t, c) for t, c in route]
            best_order: list[tuple[str, tuple[int, int]]] | None = None
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
