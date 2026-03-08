"""Speculative item pickup for idle bots on large teams.

When there are more bots than items to pick up, idle bots speculatively
grab items from shelves.  If those items match a future order the bot
can deliver immediately, shaving entire pickup-travel cycles.
"""

from typing import Any, Optional

from grocery_bot.pathfinding import DIRECTIONS
from grocery_bot.constants import (
    MAX_INVENTORY,
    PREDICTION_TEAM_MIN,
    SPEC_MAX_TEAM_COPIES,
)


class SpeculativeMixin:
    """Mixin providing speculative item pickup for idle bots."""

    def _step_speculative_pickup(self, ctx) -> bool:
        """Speculatively pick up items when idle (large teams)."""
        if len(self.bots) < PREDICTION_TEAM_MIN:
            return False
        if ctx.has_active or len(ctx.inv) >= MAX_INVENTORY:
            return False
        has_assignment = (
            ctx.bid in self.bot_assignments
            and bool(self.bot_assignments[ctx.bid])
        )
        if has_assignment:
            return False
        return self._try_speculative_pickup(
            ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.inv, ctx.blocked
        )

    def _try_speculative_pickup(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        inv: list[str],
        blocked: set[tuple[int, int]],
    ) -> bool:
        """Pick up items speculatively for future orders."""
        num_bots = len(self.bots)
        max_spec = max(num_bots // 2, 4)
        if self._speculative_pickers >= max_spec:
            return False

        team_type_count: dict[str, int] = {}
        for b in self.bots:
            for it_type in b["inventory"]:
                team_type_count[it_type] = team_type_count.get(it_type, 0) + 1

        bot_types = set(inv)
        free = MAX_INVENTORY - len(inv)
        if free <= 0:
            return False

        # Pass 1: adjacent pickup (zero travel cost — always take it)
        item = self._find_spec_adjacent(
            bx, by, bot_types, team_type_count,
        )
        if item:
            self.claimed.add(item["id"])
            self._spec_types_claimed.add(item["type"])
            self._speculative_pickers += 1
            self._emit(bid, bx, by, self._pickup(bid, item))
            return True

        # Pass 2: walk to nearest unclaimed item of an uncovered type
        target_item, target_cell = self._find_spec_target(
            pos, bot_types, team_type_count,
        )
        if not target_item or not target_cell:
            return False

        self.claimed.add(target_item["id"])
        self._spec_types_claimed.add(target_item["type"])
        self._speculative_pickers += 1
        return self._emit_move(bid, bx, by, pos, target_cell, blocked)

    def _find_spec_adjacent(
        self,
        bx: int,
        by: int,
        bot_types: set[str],
        team_type_count: dict[str, int],
    ) -> Optional[dict[str, Any]]:
        """Find an adjacent item suitable for speculative pickup."""
        for dx, dy in DIRECTIONS:
            for it in self.items_at_pos.get((bx + dx, by + dy), []):
                if not self._is_available(it):
                    continue
                t = it["type"]
                if t in self._spec_types_claimed:
                    continue
                if t in bot_types:
                    continue
                if team_type_count.get(t, 0) >= SPEC_MAX_TEAM_COPIES:
                    continue
                return it
        return None

    def _find_spec_target(
        self,
        pos: tuple[int, int],
        bot_types: set[str],
        team_type_count: dict[str, int],
    ) -> tuple[Optional[dict[str, Any]], Optional[tuple[int, int]]]:
        """Find the nearest walkable item of an uncovered type."""
        best_item: Optional[dict[str, Any]] = None
        best_cell: Optional[tuple[int, int]] = None
        best_dist: float = float("inf")
        for it in self.items:
            if not self._is_available(it):
                continue
            t = it["type"]
            if t in self._spec_types_claimed:
                continue
            if t in bot_types:
                continue
            if team_type_count.get(t, 0) >= SPEC_MAX_TEAM_COPIES:
                continue
            cell, d = self.gs.find_best_item_target(pos, it)
            if cell and d < best_dist:
                best_dist = d
                best_item = it
                best_cell = cell
        return best_item, best_cell
