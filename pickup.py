"""Pickup logic (active items, preview pre-pick, routing) for RoundPlanner."""

from itertools import permutations

from pathfinding import DIRECTIONS
from constants import (
    CASCADE_DETOUR_STEPS,
    CLUSTER_DISTANCE_WEIGHT,
    MAX_DETOUR_STEPS,
    MAX_INVENTORY,
    MEDIUM_TEAM_MIN,
)


class PickupMixin:
    """Mixin providing active item pickup, preview pre-pick, and route building."""

    def _try_active_pickup(self, bid, bx, by, pos, inv, blocked):
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

    def _build_assigned_route(self, bid, pos):
        assigned = []
        for it in self.bot_assignments[bid]:
            if it["id"] in self.claimed:
                continue
            cell, d = self.gs.find_best_item_target(pos, it)
            if cell and d < float("inf"):
                assigned.append((it, cell))
        if assigned:
            return self.gs.tsp_route(pos, assigned, self.drop_off)
        return None

    def _build_greedy_route(self, pos, inv):
        # Single-bot: use optimized item selection
        if len(self.bots) <= 1:
            return self._build_single_bot_route(pos, inv)

        candidates = []
        for it, _ in self._iter_needed_items(self.net_active):
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

        selected = []
        selected_types = {}
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

    def _build_single_bot_route(self, pos, inv):
        """Optimized route for single bot: prefer closest shelves to dropoff."""
        slots = MAX_INVENTORY - len(inv)
        if slots <= 0:
            return None

        type_shelves = {}
        for it, _ in self._iter_needed_items(self.net_active):
            t = it["type"]
            ipos = tuple(it["position"])
            best_ac = None
            best_d_drop = float("inf")
            for ac in self.gs.adj_cache.get(ipos, []):
                dd = self.gs.dist_static(ac, self.drop_off)
                if dd < best_d_drop:
                    best_d_drop = dd
                    best_ac = ac
            if best_ac is None:
                continue
            type_shelves.setdefault(t, []).append((it, best_ac, best_d_drop))

        if not type_shelves:
            return None

        type_best = {}
        for t, shelves in type_shelves.items():
            shelves.sort(key=lambda s: s[2])
            type_best[t] = shelves[0]

        candidates = []
        for t, (it, cell, d_drop) in type_best.items():
            if len(candidates) >= slots:
                break
            d_bot = self.gs.dist_static(pos, cell)
            if d_bot + 1 + d_drop >= self.rounds_left:
                continue
            candidates.append((it, cell, d_bot + d_drop))

        if not candidates:
            return None

        candidates.sort(key=lambda c: c[2])
        selected = [(it, cell) for it, cell, _ in candidates[:slots]]

        if not selected:
            return None
        return self._flexible_tsp(pos, selected, self.drop_off)

    def _flexible_tsp(self, bot_pos, item_targets, drop_off):
        """TSP that considers ALL adjacent cells per item for better routes."""
        n = len(item_targets)
        if n <= 1:
            if n == 1:
                it, _ = item_targets[0]
                ipos = tuple(it["position"])
                best_cell = None
                best_cost = float("inf")
                for ac in self.gs.adj_cache.get(ipos, []):
                    cost = self.gs.dist_static(bot_pos, ac) + self.gs.dist_static(ac, drop_off)
                    if cost < best_cost:
                        best_cost = cost
                        best_cell = ac
                if best_cell:
                    return [(it, best_cell)]
            return item_targets

        item_cells = []
        for it, default_cell in item_targets:
            ipos = tuple(it["position"])
            cells = self.gs.adj_cache.get(ipos, [default_cell])
            if not cells:
                cells = [default_cell]
            item_cells.append((it, cells))

        best_order = None
        best_cost = float("inf")

        for perm in permutations(range(n)):
            cost = 0
            prev = bot_pos
            cells_chosen = []
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

    def _cluster_select(self, candidates):
        """For same-type items, prefer the one closest to other needed items."""
        all_positions = [cell for _, cell, _ in candidates]
        if len(all_positions) < 2:
            return candidates
        cx = sum(p[0] for p in all_positions) / len(all_positions)
        cy = sum(p[1] for p in all_positions) / len(all_positions)

        by_type = {}
        for entry in candidates:
            t = entry[0]["type"]
            by_type.setdefault(t, []).append(entry)

        result = []
        for t, entries in by_type.items():
            needed = self.net_active.get(t, 0)
            if len(entries) <= needed:
                entries.sort(key=lambda e: e[2])
                result.extend(entries)
            else:
                scored = []
                for entry in entries:
                    _, cell, d = entry
                    cluster_d = abs(cell[0] - cx) + abs(cell[1] - cy)
                    scored.append((*entry, d + CLUSTER_DISTANCE_WEIGHT * cluster_d))
                scored.sort(key=lambda e: e[3])
                result.extend((it, cell, d) for it, cell, d, _ in scored)

        result.sort(key=lambda c: c[2])
        return result

    def _try_preview_prepick(self, bid, bx, by, pos, inv, blocked, force_slots=False):
        if not self.preview:
            return False
        free = MAX_INVENTORY - len(inv)
        if free <= 0:
            return False
        if not force_slots and self._spare_slots(inv) <= 0:
            return False

        is_preview_bot = (bid in self.preview_bot_ids)

        # Pass 1: check adjacent items via position lookup (free pickup)
        adj = self._find_adjacent_needed(bx, by, self.net_preview, prefer_cascade=True)
        if adj:
            self._claim(adj, self.net_preview)
            self._emit(bid, bx, by, self._pickup(bid, adj))
            return True

        # Pass 2: walk to distant preview items
        if not is_preview_bot:
            if len(self.bots) < MEDIUM_TEAM_MIN and self.active_on_shelves > 0:
                # Small teams: don't divert from active work
                return False
            max_preview_walkers = max(2, len(self.bots) // 2)
            if self._preview_walkers >= max_preview_walkers:
                return False
            self._preview_walkers += 1

        best = None
        best_dist = float("inf")
        best_cascade = False
        for it, is_cascade in self._iter_needed_items(self.net_preview):
            _, d = self.gs.find_best_item_target(pos, it)
            if is_cascade and not best_cascade:
                best, best_dist, best_cascade = it, d, True
            elif is_cascade == best_cascade and d < best_dist:
                best, best_dist = it, d

        if not best:
            return False

        self._claim(best, self.net_preview)
        target, _ = self.gs.find_best_item_target(pos, best)
        if target:
            return self._emit_move(bid, bx, by, pos, target, blocked)
        return False

    def _find_detour_item(self, pos, needed, max_detour=MAX_DETOUR_STEPS, prefer_cascade=False):
        """Find item worth detouring for on the way to drop-off."""
        direct = self.gs.dist_static(pos, self.drop_off)
        best_item = best_cell = None
        best_cost = float("inf")
        best_cascade = False

        for it, is_cascade in self._iter_needed_items(needed):
            if not prefer_cascade:
                is_cascade = False
            cell, d = self.gs.find_best_item_target(pos, it)
            if not cell:
                continue
            detour = d + self.gs.dist_static(cell, self.drop_off) - direct
            if is_cascade and not best_cascade:
                best_cost = detour
                best_item, best_cell, best_cascade = it, cell, True
            elif is_cascade == best_cascade and detour < best_cost:
                best_cost = detour
                best_item, best_cell = it, cell

        effective_max = (CASCADE_DETOUR_STEPS if best_cascade else max_detour) if prefer_cascade else max_detour
        if best_item and best_cost <= effective_max:
            return best_item, best_cell
        return None, None

    def _find_nearest_active_item_pos(self, pos):
        """Find the position of the nearest reachable active item on shelves."""
        best_cell = None
        best_d = float("inf")
        for it, _ in self._iter_needed_items(self.net_active):
            cell, d = self.gs.find_best_item_target(pos, it)
            if cell and d < best_d:
                best_d = d
                best_cell = cell
        return best_cell
