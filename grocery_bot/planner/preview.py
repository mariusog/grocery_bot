"""Preview pre-pick and detour logic for RoundPlanner."""

from typing import Any, Optional

from grocery_bot.constants import (
    CASCADE_DETOUR_STEPS,
    MAX_DETOUR_STEPS,
    MAX_INVENTORY,
    MEDIUM_TEAM_MIN,
)


class PreviewMixin:
    """Mixin providing preview pre-pick, detour finding, and nearest-item lookup."""

    def _try_preview_prepick(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        inv: list[str],
        blocked: set[tuple[int, int]],
        force_slots: bool = False,
    ) -> bool:
        if not self.preview:
            return False
        free = MAX_INVENTORY - len(inv)
        if free <= 0:
            return False
        if not force_slots and self._spare_slots(inv) <= 0:
            return False

        is_preview_bot = bid in self.preview_bot_ids

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

        best: Optional[dict[str, Any]] = None
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

    def _find_detour_item(
        self,
        pos: tuple[int, int],
        needed: dict[str, int],
        max_detour: int = MAX_DETOUR_STEPS,
        prefer_cascade: bool = False,
    ) -> tuple[Optional[dict[str, Any]], Optional[tuple[int, int]]]:
        """Find item worth detouring for on the way to drop-off."""
        direct = self.gs.dist_static(pos, self.drop_off)
        best_item: Optional[dict[str, Any]] = None
        best_cell: Optional[tuple[int, int]] = None
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

        effective_max = (
            (CASCADE_DETOUR_STEPS if best_cascade else max_detour)
            if prefer_cascade
            else max_detour
        )
        if best_item and best_cost <= effective_max:
            return best_item, best_cell
        return None, None

    def _find_nearest_active_item_pos(
        self, pos: tuple[int, int]
    ) -> Optional[tuple[int, int]]:
        """Find the position of the nearest reachable active item on shelves."""
        best_cell: Optional[tuple[int, int]] = None
        best_d = float("inf")
        for it, _ in self._iter_needed_items(self.net_active):
            cell, d = self.gs.find_best_item_target(pos, it)
            if cell and d < best_d:
                best_d = d
                best_cell = cell
        return best_cell
