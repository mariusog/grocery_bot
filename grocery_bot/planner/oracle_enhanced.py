"""Oracle-enhanced planner — extends RoundPlanner with deep oracle knowledge.

Instead of replacing the reactive planner's battle-tested 22-step chain,
this subclass adds deeper oracle lookahead in plan() setup. The parent's
existing speculative tiebreaker uses oracle_needs for prioritization.
"""

from grocery_bot.constants import ORACLE_DEEP_LOOKAHEAD
from grocery_bot.planner.round_planner import RoundPlanner


class OracleEnhancedPlanner(RoundPlanner):
    """RoundPlanner with deeper oracle lookahead.

    Overrides _compute_oracle_needs to look 6 orders ahead instead of 2,
    and uses both recorded and synthetic orders. The parent's speculative
    tiebreaker already uses oracle_needs effectively — this just gives it
    more data to work with.
    """

    def _compute_oracle_needs(self) -> None:
        """Compute item needs for orders N+2..N+K with deeper lookahead."""
        if not self.gs.future_orders:
            return
        idx = self.gs._demand_order_idx
        if idx < 0:
            return
        limit = len(self.gs.future_orders)
        for off in range(2, 2 + ORACLE_DEEP_LOOKAHEAD):
            oidx = idx + off
            if oidx >= limit:
                break
            for t in self.gs.future_orders[oidx].get("items_required", []):
                self.oracle_needs[t] = self.oracle_needs.get(t, 0) + 1

    def _oracle_idle_target(self, bid: int) -> tuple[int, int] | None:
        """Compute a target biased toward oracle-needed items."""
        if not self.oracle_needs:
            return None
        idx = self.gs._demand_order_idx
        if idx < 0:
            return None
        limit = len(self.gs.future_orders)
        target_idx = idx + 2
        if target_idx >= limit:
            return None
        order = self.gs.future_orders[target_idx]
        needed_types = set(order.get("items_required", []))
        if not needed_types:
            return None
        positions: list[tuple[int, int]] = []
        for t in needed_types:
            for it in self.items_by_type.get(t, []):
                positions.append(tuple(it["position"]))
        if not positions:
            return None
        cx = sum(p[0] for p in positions) // len(positions)
        cy = sum(p[1] for p in positions) // len(positions)
        return (cx, cy)
