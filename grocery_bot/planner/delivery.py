"""Delivery decision logic and end-game helpers for RoundPlanner."""

from grocery_bot.constants import DELIVER_WHEN_CLOSE_DIST, MAX_INVENTORY


class DeliveryMixin:
    """Mixin providing delivery timing, end-game estimation, and item maximization."""

    def _should_head_to_dropoff(self, bot: dict[str, object]) -> bool:
        """Return True when a bot is likely to prioritize delivery this round."""
        bid = int(bot["id"])
        if not self.bot_has_active.get(bid, False):
            return False

        pos = tuple(bot["position"])
        inv = bot["inventory"]
        if pos == self.drop_off:
            return True
        if self.active_on_shelves == 0 or len(inv) >= MAX_INVENTORY:
            return True
        if self.bot_roles.get(bid) == "deliver":
            return True
        if self._bot_delivery_completes_order(bot):
            return True

        d_to_drop = self.gs.dist_static(pos, self.drop_off)
        return len(inv) >= 2 and d_to_drop <= DELIVER_WHEN_CLOSE_DIST

    def _get_delivery_target(
        self,
        bid: int,
        pos: tuple[int, int],
    ) -> tuple[tuple[int, int], bool]:
        """Pick a congestion-aware dropoff target for a delivering bot."""
        delivering_bots: list[tuple[int, tuple[int, int]]] = []
        for bot in self.bots:
            if not self._should_head_to_dropoff(bot):
                continue
            obid = bot["id"]
            if obid == bid:
                ob_pos = pos
            else:
                ob_pos = self.predicted.get(obid, tuple(bot["position"]))
            delivering_bots.append((obid, ob_pos))

        if not delivering_bots:
            return self.drop_off, False

        target, should_wait = self.gs.get_dropoff_approach_target(
            bid, pos, self.drop_off, delivering_bots
        )
        if not should_wait:
            return target, False

        wait_radius = 0
        if self.gs.dropoff_wait_cells:
            wait_radius = max(
                self.gs.dist_static(cell, self.drop_off)
                for cell in self.gs.dropoff_wait_cells
            )
        if self.gs.dist_static(pos, self.drop_off) > wait_radius + 1:
            return self.drop_off, False

        return target, True

    def _emit_delivery_move_or_wait(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        blocked: set[tuple[int, int]],
    ) -> None:
        """Move toward a congestion-aware delivery target."""
        target, _ = self._get_delivery_target(bid, pos)
        self.gs.notify_bot_target(bid, target)
        if target == pos:
            self._emit(bid, bx, by, {"bot": bid, "action": "wait"})
            return
        self._emit_move_or_wait(bid, bx, by, pos, target, blocked)

    def _estimate_rounds_to_complete(
        self, pos: tuple[int, int], inv: list[str]
    ) -> float:
        """Estimate rounds needed to pick up all remaining active items and deliver.

        Divides the sequential estimate by the number of bots that can
        pick in parallel so endgame decisions are not overly pessimistic.
        """
        remaining: list[tuple[dict, tuple[int, int], float]] = []
        for it, _ in self._iter_needed_items(self.net_active):
            cell, d = self.gs.find_best_item_target(pos, it)
            if cell and d < float("inf"):
                remaining.append((it, cell, d))
        if not remaining:
            return self.gs.dist_static(pos, self.drop_off) + 1

        remaining.sort(key=lambda c: c[2])
        total_dist: float = 0
        current = pos
        picked = 0
        for it, cell, _ in remaining:
            d = self.gs.dist_static(current, cell)
            total_dist += d + 1
            current = cell
            picked += 1
            if picked + len(inv) >= MAX_INVENTORY:
                total_dist += self.gs.dist_static(current, self.drop_off) + 1
                current = self.drop_off
                picked = 0
        if picked > 0 or inv:
            total_dist += self.gs.dist_static(current, self.drop_off) + 1

        # On multi-bot teams, items are picked in parallel.  Divide the
        # sequential cost by the number of available pickers (bots without
        # active items and with free inventory), capped by the number of
        # remaining items to avoid over-optimism.
        num_pickers = max(1, sum(
            1 for b in self.bots
            if not self.bot_has_active.get(b["id"], False)
            and len(b["inventory"]) < MAX_INVENTORY
        ))
        num_pickers = min(num_pickers, max(1, len(remaining)))
        if num_pickers > 1:
            total_dist = total_dist / num_pickers
        return total_dist

    def _should_deliver_early(self, pos: tuple[int, int], inv: list[str]) -> bool:
        """Return True if delivering now and starting fresh is cheaper than filling up."""
        if not inv or self.active_on_shelves == 0:
            return False

        slots_left = MAX_INVENTORY - len(inv)

        cost_deliver = self.gs.dist_static(pos, self.drop_off) + 1

        remaining: list[tuple[dict, tuple[int, int], float]] = []
        for it, _ in self._iter_needed_items(self.net_active):
            cell, d_from_drop = self.gs.find_best_item_target(self.drop_off, it)
            if cell:
                remaining.append((it, cell, d_from_drop))

        if not remaining:
            return False

        remaining.sort(key=lambda c: c[2])
        cost_remaining: float = 0
        cur = self.drop_off
        picked = 0
        for _, cell, _ in remaining:
            cost_remaining += self.gs.dist_static(cur, cell) + 1
            cur = cell
            picked += 1
            if picked >= MAX_INVENTORY:
                cost_remaining += self.gs.dist_static(cur, self.drop_off) + 1
                cur = self.drop_off
                picked = 0
        if picked > 0:
            cost_remaining += self.gs.dist_static(cur, self.drop_off) + 1

        total_deliver_now = cost_deliver + cost_remaining

        fill_items = remaining[:slots_left]
        if not fill_items:
            return False

        cost_fill: float = 0
        cur = pos
        for _, cell, _ in fill_items:
            cost_fill += self.gs.dist_static(cur, cell) + 1
            cur = cell
        cost_fill += self.gs.dist_static(cur, self.drop_off) + 1

        leftover = remaining[slots_left:]
        cur = self.drop_off
        picked = 0
        for _, cell, _ in leftover:
            cost_fill += self.gs.dist_static(cur, cell) + 1
            cur = cell
            picked += 1
            if picked >= MAX_INVENTORY:
                cost_fill += self.gs.dist_static(cur, self.drop_off) + 1
                cur = self.drop_off
                picked = 0
        if picked > 0:
            cost_fill += self.gs.dist_static(cur, self.drop_off) + 1

        return total_deliver_now < cost_fill - 2

    def _try_maximize_items(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        inv: list[str],
        blocked: set[tuple[int, int]],
    ) -> bool:
        """End-game: maximize individual item deliveries when order can't complete."""
        has_active = self.bot_has_active[bid]
        if has_active and len(inv) > 0:
            nearest = self._find_nearest_active_item_pos(pos)
            if nearest:
                d_to_item = self.gs.dist_static(pos, nearest)
                d_item_to_drop = self.gs.dist_static(nearest, self.drop_off)
                total_with_pickup = d_to_item + 1 + d_item_to_drop + 1
                if total_with_pickup < self.rounds_left and len(inv) < MAX_INVENTORY:
                    return False

            self._emit_delivery_move_or_wait(bid, bx, by, pos, blocked)
            return True

        # Bots with preview-only inventory: deliver for +1/item during endgame
        if not has_active and len(inv) > 0:
            d_to_drop = self.gs.dist_static(pos, self.drop_off)
            if d_to_drop + 1 < self.rounds_left:
                self._emit_move_or_wait(bid, bx, by, pos, self.drop_off, blocked)
                return True

        return False
