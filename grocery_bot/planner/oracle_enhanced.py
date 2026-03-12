"""Oracle-enhanced planner — extends RoundPlanner with deep oracle knowledge.

Instead of replacing the reactive planner's battle-tested 22-step chain,
this subclass adds oracle pre-computation in plan() setup and biases
existing steps via oracle_item_value scores.
"""

from typing import Any

from grocery_bot.constants import (
    ORACLE_DEEP_LOOKAHEAD,
    SPEC_MAX_TEAM_COPIES,
)
from grocery_bot.planner.round_planner import RoundPlanner


class OracleEnhancedPlanner(RoundPlanner):
    """RoundPlanner with oracle knowledge enhancements.

    Adds deep oracle needs computation and per-item-type future demand
    scoring. All 22 existing steps run unchanged; oracle knowledge only
    biases tiebreakers in speculative pickup, idle positioning, and
    assignment.
    """

    def plan(self) -> list[dict[str, Any]]:
        """Extend parent plan() with oracle pre-computation."""
        # Run parent plan setup (which calls _compute_needs -> _compute_oracle_needs)
        # We override _compute_oracle_needs to go deeper, but we also need
        # to compute item values AFTER _compute_needs populates items_by_type.
        # Strategy: let parent plan() run fully, but override the oracle
        # computation via _compute_oracle_needs, and compute item values
        # right after _compute_needs by hooking into plan().

        # We need to intercept after _compute_needs but before the bot loop.
        # Simplest: call super().plan() which does everything, but override
        # _compute_oracle_needs for deeper lookahead.
        # For oracle_item_value, override _compute_needs to call super + extra.
        return super().plan()

    def _compute_oracle_needs(self) -> None:
        """Compute item needs for orders N+2..N+K with deeper lookahead."""
        if not self.gs.future_orders:
            return
        idx = self.gs._demand_order_idx
        if idx < 0:
            return
        limit = self.gs.future_orders_recorded
        for off in range(2, 2 + ORACLE_DEEP_LOOKAHEAD):
            oidx = idx + off
            if oidx >= limit:
                break
            for t in self.gs.future_orders[oidx].get("items_required", []):
                self.oracle_needs[t] = self.oracle_needs.get(t, 0) + 1
        self._compute_oracle_item_value()

    def _compute_oracle_item_value(self) -> None:
        """Score each item type by how many future orders need it.

        Produces oracle_item_value: dict[str, float] where higher = more
        valuable for future orders. Only counts items actually on shelves.
        """
        self.oracle_item_value = {}
        if not self.oracle_needs:
            return
        for item_type, count in self.oracle_needs.items():
            if item_type in self.items_by_type:
                self.oracle_item_value[item_type] = float(count)

    def _step_clear_nonactive_inventory(self, ctx: Any) -> bool:
        """Oracle-aware: hold items matching upcoming orders."""
        if ctx.has_active or len(ctx.inv) == 0 or self.active_on_shelves == 0:
            return False
        # Check if carried items are valuable for upcoming orders
        if self.oracle_item_value and not ctx.has_active:
            valuable_count = sum(1 for t in ctx.inv if self.oracle_item_value.get(t, 0) > 0)
            # Hold items if ALL carried items are oracle-valuable
            # and we're not clogging (still have assignment capacity)
            if valuable_count == len(ctx.inv):
                has_assignment = ctx.bid in self.bot_assignments and bool(
                    self.bot_assignments[ctx.bid]
                )
                if not has_assignment:
                    return False
        # Fall through to parent behavior
        return super()._step_clear_nonactive_inventory(ctx)

    def _find_spec_target(
        self,
        pos: tuple[int, int],
        bot_types: set[str],
        team_type_count: dict[str, int],
    ) -> tuple[dict[str, Any] | None, tuple[int, int] | None]:
        """Oracle-enhanced: rank by future demand, not just distance."""
        best_item: dict[str, Any] | None = None
        best_cell: tuple[int, int] | None = None
        best_key: tuple[int, float, float] = (2, 0.0, float("inf"))
        for it in self.items:
            if not self._is_available(it):
                continue
            t = it["type"]
            if t in self._spec_types_claimed or t in bot_types:
                continue
            if team_type_count.get(t, 0) >= SPEC_MAX_TEAM_COPIES:
                continue
            cell, d = self.gs.find_best_item_target(pos, it)
            is_preview = (
                self.cfg.prefer_preview_spec and self.preview and self.net_preview.get(t, 0) > 0
            )
            oracle_weight = self.oracle_item_value.get(t, 0)
            # Tier 0: preview. Tier 1: oracle-known. Tier 2: unknown.
            tier = 0 if is_preview else (1 if oracle_weight > 0 else 2)
            # Within same tier, prefer higher oracle value, then shorter distance
            key = (tier, -oracle_weight, d)
            if cell and key < best_key:
                best_key = key
                best_item = it
                best_cell = cell
        return best_item, best_cell

    def _oracle_idle_target(self, bid: int) -> tuple[int, int] | None:
        """Compute a target position biased toward oracle-needed items."""
        if not self.oracle_item_value:
            return None
        # Find items for the first oracle-only order (N+2)
        idx = self.gs._demand_order_idx
        if idx < 0:
            return None
        limit = self.gs.future_orders_recorded
        target_idx = idx + 2  # first order beyond preview
        if target_idx >= limit:
            return None
        order = self.gs.future_orders[target_idx]
        needed_types = set(order.get("items_required", []))
        if not needed_types:
            return None
        # Compute centroid of matching items on the map
        positions: list[tuple[int, int]] = []
        for t in needed_types:
            for it in self.items_by_type.get(t, []):
                positions.append(tuple(it["position"]))
        if not positions:
            return None
        cx = sum(p[0] for p in positions) // len(positions)
        cy = sum(p[1] for p in positions) // len(positions)
        return (cx, cy)


# Populate step chain: same as RoundPlanner but with oracle clear override.
# The step chain is inherited from RoundPlanner — _step_clear_nonactive_inventory
# is already overridden as a method, so the parent's step chain calls our version.
