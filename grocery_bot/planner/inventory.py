"""Inventory allocation mixin for RoundPlanner."""

from typing import Any

from grocery_bot.planner._base import PlannerBase


class InventoryMixin(PlannerBase):
    """Mixin providing inventory allocation helpers."""

    def _count_usable_inventory(
        self,
        bot: dict[str, Any],
        remaining: dict[str, int],
        reserved: dict[str, int] | None = None,
    ) -> tuple[int, int]:
        """Count inventory copies that can still satisfy the remaining need."""
        skip = dict(reserved or {})
        useful_total = 0
        useful_types: set[str] = set()

        for item in bot["inventory"]:
            if skip.get(item, 0) > 0:
                skip[item] -= 1
                continue
            if remaining.get(item, 0) <= 0:
                continue
            useful_total += 1
            useful_types.add(item)

        return useful_total, len(useful_types)

    def _allocate_carried_need(
        self,
        needed: dict[str, int],
        reserved_by_bot: dict[int, dict[str, int]] | None = None,
    ) -> tuple[dict[str, int], dict[int, dict[str, int]], dict[str, int]]:
        """Allocate carried inventory copies to the still-undelivered order need.

        A carried item only counts as active if it is actually useful toward the
        remaining order. Distinct coverage is prioritized first so mixed
        inventories stay active while pure duplicate carriers fall back to
        non-active behavior once the order is already covered.
        """
        remaining: dict[str, int] = {
            item_type: count for item_type, count in needed.items() if count > 0
        }
        reserved_by_bot = reserved_by_bot or {}

        allocated_total: dict[str, int] = {}
        allocated_by_bot: dict[int, dict[str, int]] = {b["id"]: {} for b in self.bots}
        pending = list(self.bots)

        while pending and remaining:
            ranked: list[tuple[int, float, int, int, dict[str, Any]]] = []
            for bot in pending:
                useful_total, useful_types = self._count_usable_inventory(
                    bot, remaining, reserved_by_bot.get(bot["id"])
                )
                if useful_total <= 0:
                    continue
                bpos = tuple(bot["position"])
                d_to_drop = self.gs.dist_static(bpos, self._nearest_dropoff(bpos))
                ranked.append((-useful_types, d_to_drop, -useful_total, bot["id"], bot))

            if not ranked:
                break

            _, _, _, _, bot = min(ranked)
            pending = [cand for cand in pending if cand["id"] != bot["id"]]

            skip = dict(reserved_by_bot.get(bot["id"], {}))
            bot_allocated: dict[str, int] = {}
            for item in bot["inventory"]:
                if skip.get(item, 0) > 0:
                    skip[item] -= 1
                    continue
                if remaining.get(item, 0) <= 0:
                    continue
                bot_allocated[item] = bot_allocated.get(item, 0) + 1
                allocated_total[item] = allocated_total.get(item, 0) + 1
                remaining[item] -= 1
                if remaining[item] <= 0:
                    del remaining[item]

            allocated_by_bot[bot["id"]] = bot_allocated

        return allocated_total, allocated_by_bot, remaining
