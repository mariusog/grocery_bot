"""Preview pre-pick and detour logic for RoundPlanner."""

from typing import Any

from grocery_bot.constants import (
    CASCADE_DETOUR_STEPS,
    MAX_DETOUR_STEPS,
    MAX_INVENTORY,
)
from grocery_bot.planner._base import PlannerBase


class PreviewMixin(PlannerBase):
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
        force_walkers: bool = False,
    ) -> bool:
        if not self.preview:
            return False
        free = MAX_INVENTORY - len(inv)
        if free <= 0:
            return False
        if not force_slots and self._spare_slots(inv, bid) <= 0:
            return False

        is_preview_bot = bid in self.preview_bot_ids

        # Pass 1: check adjacent items via position lookup (free pickup)
        adj = self._find_adjacent_needed(bx, by, self.net_preview, prefer_cascade=True)
        if adj:
            self._claim(adj, self.net_preview)
            self._emit(bid, bx, by, self._pickup(bid, adj))
            return True

        # Pass 2: walk to distant preview items
        if not is_preview_bot and not force_walkers:
            if self.cfg.num_bots <= 5 and self.active_on_shelves > 0:
                # Small/medium teams (≤5): don't divert from active work
                return False
            max_walkers = self.cfg.max_walkers(self.active_on_shelves)
            if self._preview_walkers >= max_walkers:
                return False
            self._preview_walkers += 1

        best: dict[str, Any] | None = None
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
    ) -> tuple[dict[str, Any] | None, tuple[int, int] | None]:
        """Find item worth detouring for on the way to drop-off."""
        nd = self._nearest_dropoff(pos)
        direct = self.gs.dist_static(pos, nd)
        best_item: dict[str, Any] | None = None
        best_cell: tuple[int, int] | None = None
        best_cost = float("inf")
        best_cascade = False

        for it, is_cascade in self._iter_needed_items(needed):
            if not prefer_cascade:
                is_cascade = False
            cell, d = self.gs.find_best_item_target(pos, it)
            if not cell:
                continue
            detour = d + self.gs.dist_static(cell, self._nearest_dropoff(cell)) - direct
            if is_cascade and not best_cascade:
                best_cost = detour
                best_item, best_cell, best_cascade = it, cell, True
            elif is_cascade == best_cascade and detour < best_cost:
                best_cost = detour
                best_item, best_cell = it, cell

        effective_max = (
            (CASCADE_DETOUR_STEPS if best_cascade else max_detour) if prefer_cascade else max_detour
        )
        if best_item and best_cost <= effective_max:
            return best_item, best_cell
        return None, None

    def _find_nearest_active_item_pos(self, pos: tuple[int, int]) -> tuple[int, int] | None:
        """Find the position of the nearest reachable active item on shelves."""
        best_cell: tuple[int, int] | None = None
        best_d = float("inf")
        for it, _ in self._iter_needed_items(self.net_active):
            cell, d = self.gs.find_best_item_target(pos, it)
            if cell and d < best_d:
                best_d = d
                best_cell = cell
        return best_cell
