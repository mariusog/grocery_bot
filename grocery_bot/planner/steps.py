"""Decision step methods for the RoundPlanner step chain."""


from grocery_bot.pathfinding import DIRECTIONS
from grocery_bot.constants import (
    CASCADE_DETOUR_STEPS,
    DELIVER_WHEN_CLOSE_DIST,
    LARGE_TEAM_MIN,
    MAX_DETOUR_STEPS,
    MAX_INVENTORY,
    MAX_NONACTIVE_DELIVERERS,
    MEDIUM_TEAM_MIN,
    MIN_INV_FOR_NONACTIVE_DELIVERY,
    PREDICTION_TEAM_MIN,
    SMALL_TEAM_MAX,
)


class StepsMixin:
    """Mixin providing all _step_* decision methods for the step chain."""

    def _step_preview_bot(self, ctx) -> bool:
        """Dedicated preview bot skips active items entirely."""
        if ctx.bid not in self.preview_bot_ids or ctx.has_active:
            return False
        if len(ctx.inv) < MAX_INVENTORY:
            for dx, dy in DIRECTIONS:
                for it in self.items_at_pos.get((ctx.bx + dx, ctx.by + dy), []):
                    if (
                        self._is_available(it)
                        and self.net_active.get(it["type"], 0) > 0
                    ):
                        self._claim(it, self.net_active)
                        self._emit(ctx.bid, ctx.bx, ctx.by, self._pickup(ctx.bid, it))
                        return True
        if self._spare_slots(ctx.inv) > 0:
            if self._try_preview_prepick(
                ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.inv, ctx.blocked
            ):
                return True
        return False

    def _step_deliver_at_dropoff(self, ctx) -> bool:
        """At drop-off with active items -> deliver."""
        if ctx.pos == self.drop_off and ctx.has_active:
            self._emit(ctx.bid, ctx.bx, ctx.by, {"bot": ctx.bid, "action": "drop_off"})
            return True
        return False

    def _step_deliver_completes_order(self, ctx) -> bool:
        """Deliver partial items if it COMPLETES the order (+5 bonus)."""
        if (
            ctx.has_active
            and self.active_on_shelves > 0
            and len(ctx.inv) < MAX_INVENTORY
            and self._bot_delivery_completes_order(ctx.bot)
        ):
            self._emit_delivery_move_or_wait(
                ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.blocked
            )
            return True
        return False

    def _step_rush_deliver(self, ctx) -> bool:
        """All active items picked up -> rush to deliver."""
        if not (ctx.has_active and self.active_on_shelves == 0):
            return False

        is_queue_front = True
        if len(self.bots) >= PREDICTION_TEAM_MIN and self._use_coordination:
            gs = self.gs
            max_deliverers = max(2, len(self.bots) // 4)
            queue_front = set(gs.delivery_queue[:max_deliverers])
            is_queue_front = ctx.bid in queue_front

        if self.preview and len(ctx.inv) < MAX_INVENTORY:
            adj = self._find_adjacent_needed(
                ctx.bx, ctx.by, self.net_preview, prefer_cascade=True
            )
            if adj:
                self._claim(adj, self.net_preview)
                self._emit(ctx.bid, ctx.bx, ctx.by, self._pickup(ctx.bid, adj))
                return True
            max_detour = MAX_DETOUR_STEPS
            if not is_queue_front:
                max_detour = CASCADE_DETOUR_STEPS
            item, cell = self._find_detour_item(
                ctx.pos, self.net_preview, max_detour=max_detour,
                prefer_cascade=True
            )
            if item:
                self._claim(item, self.net_preview)
                if self._emit_move(ctx.bid, ctx.bx, ctx.by, ctx.pos, cell, ctx.blocked):
                    return True
        self._emit_delivery_move_or_wait(
            ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.blocked
        )
        return True

    def _step_opportunistic_preview(self, ctx) -> bool:
        """Opportunistic adjacent preview pickup (spare slots only)."""
        if not (
            self.preview
            and self._spare_slots(ctx.inv) > 0
            and not (len(self.bots) == 1 and self.active_on_shelves > 1)
        ):
            return False
        adj = self._find_adjacent_needed(
            ctx.bx, ctx.by, self.net_preview, prefer_cascade=True
        )
        if adj:
            self._claim(adj, self.net_preview)
            self._emit(ctx.bid, ctx.bx, ctx.by, self._pickup(ctx.bid, adj))
            return True
        return False

    def _step_inventory_full_deliver(self, ctx) -> bool:
        """Inventory full -> deliver."""
        if not (ctx.has_active and len(ctx.inv) >= MAX_INVENTORY):
            return False
        self._emit_delivery_move_or_wait(
            ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.blocked
        )
        return True

    def _step_zero_cost_delivery(self, ctx) -> bool:
        """Zero-cost delivery -- deliver if adjacent to dropoff."""
        if not (
            ctx.has_active
            and ctx.pos != self.drop_off
            and self.gs.dist_static(ctx.pos, self.drop_off) == 1
            and not self._bot_delivery_completes_order(ctx.bot)
        ):
            return False
        next_item_pos = self._find_nearest_active_item_pos(ctx.pos)
        if next_item_pos is not None:
            dist_via_dropoff = 1 + self.gs.dist_static(self.drop_off, next_item_pos)
            dist_direct = self.gs.dist_static(ctx.pos, next_item_pos)
            if dist_via_dropoff <= dist_direct + 1:
                self._emit_delivery_move_or_wait(
                    ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.blocked
                )
                return True
        return False

    def _step_endgame(self, ctx) -> bool:
        """Improved end-game strategy."""
        if not (self.endgame and ctx.inv):
            return False
        d = self.gs.dist_static(ctx.pos, self.drop_off)
        if d + 1 >= self.rounds_left:
            if ctx.has_active:
                self._emit_delivery_move_or_wait(
                    ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.blocked
                )
            else:
                self._emit_move_or_wait(
                    ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked
                )
            return True
        if ctx.has_active and self.active_on_shelves > 0:
            rounds_to_complete = self._estimate_rounds_to_complete(ctx.pos, ctx.inv)
            if rounds_to_complete > self.rounds_left:
                if self._try_maximize_items(
                    ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.inv, ctx.blocked
                ):
                    return True
        return False

    def _step_active_pickup(self, ctx) -> bool:
        """Pick up active items (adjacent first, then TSP route)."""
        return self._try_active_pickup(
            ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.inv, ctx.blocked
        )

    def _step_deliver_active(self, ctx) -> bool:
        """Deliver active items."""
        if not ctx.has_active:
            return False
        d_to_drop = self.gs.dist_static(ctx.pos, self.drop_off)

        if (
            self.active_on_shelves > 0
            and len(ctx.inv) >= 2
            and d_to_drop <= DELIVER_WHEN_CLOSE_DIST
        ):
            self._emit_delivery_move_or_wait(
                ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.blocked
            )
            return True

        spare = self._spare_slots(ctx.inv)
        if self.preview and spare > 0 and not self.order_nearly_complete:
            item, cell = self._find_detour_item(ctx.pos, self.net_preview)
            if item:
                self._claim(item, self.net_preview)
                if self._emit_move(ctx.bid, ctx.bx, ctx.by, ctx.pos, cell, ctx.blocked):
                    return True
        self._emit_delivery_move_or_wait(
            ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.blocked
        )
        return True

    def _step_clear_nonactive_inventory(self, ctx) -> bool:
        """Bot has non-active items clogging inventory."""
        if ctx.has_active or len(ctx.inv) == 0 or self.active_on_shelves == 0:
            return False

        num_bots = len(self.bots)
        if num_bots <= SMALL_TEAM_MAX:
            if len(ctx.inv) < MIN_INV_FOR_NONACTIVE_DELIVERY:
                return False
        elif num_bots < PREDICTION_TEAM_MIN:
            if len(ctx.inv) < MAX_INVENTORY:
                return False
        else:
            # Large teams: only clear when inventory is completely full
            if len(ctx.inv) < MAX_INVENTORY:
                return False

        # Purely non-active inventory cannot be delivered; sitting on the
        # dropoff and spamming drop_off only blocks real deliverers.
        if ctx.pos == self.drop_off:
            return False
        if (
            num_bots >= MEDIUM_TEAM_MIN
            and self._nonactive_delivering >= MAX_NONACTIVE_DELIVERERS
        ):
            return False
        self._nonactive_delivering += 1
        self._emit_move_or_wait(
            ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked
        )
        return True

    def _step_preview_prepick(self, ctx) -> bool:
        """Pre-pick preview items."""
        num_bots = len(self.bots)
        if num_bots >= PREDICTION_TEAM_MIN:
            # Medium-large teams: unassigned bots prepick freely.
            # Very large teams (16+): only force when active items are done.
            has_assignment = (
                ctx.bid in self.bot_assignments
                and bool(self.bot_assignments[ctx.bid])
            )
            if num_bots <= 15:
                force = not has_assignment and not ctx.has_active
            else:
                force = self.active_on_shelves == 0
        elif num_bots >= LARGE_TEAM_MIN:
            force = self.active_on_shelves == 0
        elif num_bots >= SMALL_TEAM_MAX:
            force = self.active_on_shelves <= 1
        else:
            force = False
        return self._try_preview_prepick(
            ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.inv, ctx.blocked, force_slots=force
        )

    def _step_clear_dropoff(self, ctx) -> bool:
        """Clear dropoff area when idle."""
        return self._try_clear_dropoff(ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.blocked)

    def _step_idle_nonactive_deliver(self, ctx) -> bool:
        """Idle bot with non-active inventory -- deliver for points."""
        if not (
            ctx.inv
            and not ctx.has_active
            and len(ctx.inv) >= MIN_INV_FOR_NONACTIVE_DELIVERY
        ):
            return False
        # Non-active items are not deliverable. If this bot reaches the
        # dropoff, let clear-dropoff/idle logic move it away instead.
        if ctx.pos == self.drop_off:
            return False
        if (
            len(self.bots) >= MEDIUM_TEAM_MIN
            and self._nonactive_delivering >= MAX_NONACTIVE_DELIVERERS
        ):
            return False
        self._nonactive_delivering += 1
        self._emit_move_or_wait(
            ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked
        )
        return True

    def _step_idle_positioning(self, ctx) -> bool:
        """Idle bot positioning -- spread out from other bots."""
        if len(self.bots) > 1:
            return self._try_idle_positioning(
                ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.blocked
            )
        return False
