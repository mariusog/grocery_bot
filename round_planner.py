"""RoundPlanner — per-round decision orchestration for all bots."""

from collections import deque, namedtuple

from pathfinding import DIRECTIONS
from orders import get_needed_items

from movement import MovementMixin
from assignment import AssignmentMixin
from pickup import PickupMixin
from delivery import DeliveryMixin
from idle import IdleMixin
from constants import (
    BOT_HISTORY_MAXLEN,
    DELIVER_WHEN_CLOSE_DIST,
    ENDGAME_ROUNDS_LEFT,
    LARGE_TEAM_MIN,
    MAX_INVENTORY,
    MAX_NONACTIVE_DELIVERERS,
    MEDIUM_TEAM_MIN,
    MIN_INV_FOR_NONACTIVE_DELIVERY,
    ORDER_NEARLY_COMPLETE_MAX,
    PICKUP_FAIL_BLACKLIST_THRESHOLD,
    SMALL_TEAM_MAX,
)

# Bundles per-bot context passed through the step chain.
BotContext = namedtuple("BotContext", "bot bid bx by pos inv blocked has_active")


class RoundPlanner(MovementMixin, AssignmentMixin, PickupMixin, DeliveryMixin, IdleMixin):
    """Plans actions for all bots in a single round.

    Encapsulates per-round mutable state (claims, predictions, net needs)
    and provides reusable methods for common item search patterns.
    """

    def __init__(self, gs, state, full_state=None):
        self.gs = gs
        self.full_state = full_state if full_state is not None else state
        self.bots = state["bots"]
        self.items = state["items"]
        self.orders = state["orders"]
        self.drop_off = tuple(state["drop_off"])
        self.current_round = state["round"]
        self.rounds_left = state["max_rounds"] - state["round"]
        self.endgame = self.rounds_left <= ENDGAME_ROUNDS_LEFT

        # Precomputed lookups
        self.bots_by_id = {b["id"]: b for b in self.bots}
        self.items_at_pos = {}
        for it in self.items:
            p = tuple(it["position"])
            self.items_at_pos.setdefault(p, []).append(it)

        # Per-round mutable state
        self.actions = []
        self.predicted = {}  # bot_id -> predicted (x, y)
        self.claimed = set()  # item IDs claimed this round
        self._yield_to = set()  # positions of higher-urgency bots to avoid
        self._nonactive_delivering = 0  # count of bots delivering non-active inventory
        self._preview_walkers = 0  # count of non-preview bots walking to preview items

    def plan(self):
        """Main entry: return list of action dicts for all bots."""
        gen = id(self.gs.dist_cache)
        needs_reset = (
            not hasattr(self.gs, 'bot_history')
            or not hasattr(self.gs, '_history_gen')
            or self.gs._history_gen != gen
        )
        if needs_reset:
            self.gs.bot_history = {}
            self.gs._history_gen = gen

        for b in self.bots:
            bid = b["id"]
            pos = tuple(b["position"])
            if bid not in self.gs.bot_history:
                self.gs.bot_history[bid] = deque(maxlen=BOT_HISTORY_MAXLEN)
            self.gs.bot_history[bid].append(pos)

        self._detect_pickup_failures()

        if self.gs.blocked_static is None:
            self.gs.init_static(
                {"grid": self._state_grid(), "items": self.items}
            )

        self.active = next(
            (o for o in self.orders
             if o.get("status") == "active" and not o["complete"]),
            None,
        )
        self.preview = next(
            (o for o in self.orders if o.get("status") == "preview"), None
        )

        if not self.active:
            return [{"bot": b["id"], "action": "wait"} for b in self.bots]

        self._compute_needs()
        self._compute_bot_assignments()
        self._pre_predict()

        urgency = {b["id"]: self._bot_urgency(b) for b in self.bots}

        for bot in self.bots:
            bid = bot["id"]
            self._yield_to = set()
            for b in self.bots:
                if b["id"] == bid or b["id"] in self.predicted:
                    continue
                if urgency[b["id"]] < urgency[bid]:
                    self._yield_to.add(tuple(b["position"]))

            self._decide_bot(bot)

        return self.actions

    def _state_grid(self):
        """Extract grid from the state for init_static compatibility."""
        return self.full_state["grid"]

    # ------------------------------------------------------------------
    # Initialization helpers
    # ------------------------------------------------------------------

    def _detect_pickup_failures(self):
        gs = self.gs
        for b in self.bots:
            bid = b["id"]
            if bid not in gs.last_pickup:
                continue
            last_item_id, last_inv_len = gs.last_pickup[bid]
            if len(b["inventory"]) <= last_inv_len:
                gs.pickup_fail_count[last_item_id] = (
                    gs.pickup_fail_count.get(last_item_id, 0) + 1
                )
                if gs.pickup_fail_count[last_item_id] >= PICKUP_FAIL_BLACKLIST_THRESHOLD:
                    gs.blacklisted_items.add(last_item_id)
            else:
                gs.pickup_fail_count.pop(last_item_id, None)
            del gs.last_pickup[bid]

    def _compute_needs(self):
        self.active_needed = get_needed_items(self.active)
        preview_needed = get_needed_items(self.preview) if self.preview else {}

        self.items_by_type = {}
        for it in self.items:
            self.items_by_type.setdefault(it["type"], []).append(it)

        carried_active = {}
        carried_preview = {}
        self.bot_has_active = {}
        self.bot_carried_active = {}
        for bot in self.bots:
            has = False
            bot_active = {}
            for inv_item in bot["inventory"]:
                if self.active_needed.get(inv_item, 0) > 0:
                    carried_active[inv_item] = carried_active.get(inv_item, 0) + 1
                    bot_active[inv_item] = bot_active.get(inv_item, 0) + 1
                    has = True
                elif inv_item in preview_needed:
                    carried_preview[inv_item] = carried_preview.get(inv_item, 0) + 1
            self.bot_has_active[bot["id"]] = has
            self.bot_carried_active[bot["id"]] = bot_active

        self.net_active = {
            t: c - carried_active.get(t, 0)
            for t, c in self.active_needed.items()
            if c - carried_active.get(t, 0) > 0
        }
        self.active_on_shelves = sum(self.net_active.values())

        self.net_preview = {
            t: c - carried_preview.get(t, 0)
            for t, c in preview_needed.items()
            if c - carried_preview.get(t, 0) > 0
        }
        self.active_types = set(self.active_needed.keys())
        self.order_nearly_complete = 0 < self.active_on_shelves <= ORDER_NEARLY_COMPLETE_MAX

        idle_bots = sum(
            1 for bot in self.bots
            if not self._is_delivering(bot)
        )
        total = self.active_on_shelves
        self.max_claim = (
            max(1, (total + idle_bots - 1) // idle_bots) if idle_bots > 0 else MAX_INVENTORY
        )

        self.preview_bot_id = None
        self.preview_bot_ids = set()
        if (self.order_nearly_complete and len(self.bots) >= 2
                and self.preview and self.net_preview):
            self._assign_preview_bot()

    # ------------------------------------------------------------------
    # Per-bot decision (steps 1-8)
    # ------------------------------------------------------------------

    # Step chain: each method returns True if it handled the bot.
    _STEP_CHAIN = None  # populated after class definition

    def _decide_bot(self, bot):
        ctx = self._build_bot_context(bot)
        for step in self._STEP_CHAIN:
            if step(self, ctx):
                return
        self._emit(ctx.bid, ctx.bx, ctx.by, {"bot": ctx.bid, "action": "wait"})

    def _build_bot_context(self, bot):
        bid = bot["id"]
        bx, by = bot["position"]
        return BotContext(
            bot=bot,
            bid=bid,
            bx=bx,
            by=by,
            pos=(bx, by),
            inv=bot["inventory"],
            blocked=self._build_blocked(bid),
            has_active=self.bot_has_active[bid],
        )

    # ------------------------------------------------------------------
    # Individual decision steps
    # ------------------------------------------------------------------

    def _step_preview_bot(self, ctx):
        """Phase 2.2: dedicated preview bot skips active items entirely."""
        if ctx.bid not in self.preview_bot_ids or ctx.has_active:
            return False
        if len(ctx.inv) < MAX_INVENTORY:
            for dx, dy in DIRECTIONS:
                for it in self.items_at_pos.get((ctx.bx + dx, ctx.by + dy), []):
                    if self._is_available(it) and self.net_active.get(it["type"], 0) > 0:
                        self._claim(it, self.net_active)
                        self._emit(ctx.bid, ctx.bx, ctx.by, self._pickup(ctx.bid, it))
                        return True
        if self._spare_slots(ctx.inv) > 0:
            if self._try_preview_prepick(ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.inv, ctx.blocked):
                return True
        return False

    def _step_deliver_at_dropoff(self, ctx):
        """Step 1: at drop-off with active items -> deliver."""
        if ctx.pos == self.drop_off and ctx.has_active:
            self._emit(ctx.bid, ctx.bx, ctx.by, {"bot": ctx.bid, "action": "drop_off"})
            return True
        return False

    def _step_deliver_completes_order(self, ctx):
        """Phase 4.4: deliver partial items if it COMPLETES the order (+5 bonus)."""
        if (ctx.has_active and self.active_on_shelves > 0
                and len(ctx.inv) < MAX_INVENTORY
                and self._bot_delivery_completes_order(ctx.bot)):
            self._emit_move_or_wait(ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked)
            return True
        return False

    def _step_rush_deliver(self, ctx):
        """Step 2: all active items picked up -> rush to deliver."""
        if not (ctx.has_active and self.active_on_shelves == 0):
            return False
        if self.preview and len(ctx.inv) < MAX_INVENTORY:
            adj = self._find_adjacent_needed(
                ctx.bx, ctx.by, self.net_preview, prefer_cascade=True
            )
            if adj:
                self._claim(adj, self.net_preview)
                self._emit(ctx.bid, ctx.bx, ctx.by, self._pickup(ctx.bid, adj))
                return True
            item, cell = self._find_detour_item(
                ctx.pos, self.net_preview, prefer_cascade=True
            )
            if item:
                self._claim(item, self.net_preview)
                if self._emit_move(ctx.bid, ctx.bx, ctx.by, ctx.pos, cell, ctx.blocked):
                    return True
        self._emit_move_or_wait(ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked)
        return True

    def _step_opportunistic_preview(self, ctx):
        """Step 3: opportunistic adjacent preview pickup (spare slots only)."""
        if not (self.preview and self._spare_slots(ctx.inv) > 0
                and not (len(self.bots) == 1 and self.active_on_shelves > 1)):
            return False
        adj = self._find_adjacent_needed(
            ctx.bx, ctx.by, self.net_preview, prefer_cascade=True
        )
        if adj:
            self._claim(adj, self.net_preview)
            self._emit(ctx.bid, ctx.bx, ctx.by, self._pickup(ctx.bid, adj))
            return True
        return False

    def _step_inventory_full_deliver(self, ctx):
        """Step 3b: inventory full -> deliver."""
        if ctx.has_active and len(ctx.inv) >= MAX_INVENTORY:
            self._emit_move_or_wait(ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked)
            return True
        return False

    def _step_zero_cost_delivery(self, ctx):
        """Phase 4.4: zero-cost delivery -- deliver if adjacent to dropoff."""
        if not (ctx.has_active and ctx.pos != self.drop_off
                and self.gs.dist_static(ctx.pos, self.drop_off) == 1
                and not self._bot_delivery_completes_order(ctx.bot)):
            return False
        next_item_pos = self._find_nearest_active_item_pos(ctx.pos)
        if next_item_pos is not None:
            dist_via_dropoff = 1 + self.gs.dist_static(self.drop_off, next_item_pos)
            dist_direct = self.gs.dist_static(ctx.pos, next_item_pos)
            if dist_via_dropoff <= dist_direct + 1:
                self._emit_move_or_wait(
                    ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked
                )
                return True
        return False

    def _step_endgame(self, ctx):
        """Phase 4.3: improved end-game strategy."""
        if not (self.endgame and ctx.inv):
            return False
        d = self.gs.dist_static(ctx.pos, self.drop_off)
        if d + 1 >= self.rounds_left:
            self._emit_move_or_wait(ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked)
            return True
        if ctx.has_active and self.active_on_shelves > 0:
            rounds_to_complete = self._estimate_rounds_to_complete(ctx.pos, ctx.inv)
            if rounds_to_complete > self.rounds_left:
                if self._try_maximize_items(ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.inv, ctx.blocked):
                    return True
        return False

    def _step_active_pickup(self, ctx):
        """Step 4: pick up active items (adjacent first, then TSP route)."""
        return self._try_active_pickup(ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.inv, ctx.blocked)

    def _step_deliver_active(self, ctx):
        """Step 5: deliver active items."""
        if not ctx.has_active:
            return False
        d_to_drop = self.gs.dist_static(ctx.pos, self.drop_off)
        if (self.active_on_shelves > 0 and len(ctx.inv) >= 2
                and d_to_drop <= DELIVER_WHEN_CLOSE_DIST):
            self._emit_move_or_wait(ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked)
            return True

        spare = self._spare_slots(ctx.inv)
        if self.preview and spare > 0 and not self.order_nearly_complete:
            item, cell = self._find_detour_item(ctx.pos, self.net_preview)
            if item:
                self._claim(item, self.net_preview)
                if self._emit_move(ctx.bid, ctx.bx, ctx.by, ctx.pos, cell, ctx.blocked):
                    return True
        self._emit_move_or_wait(ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked)
        return True

    def _step_clear_nonactive_inventory(self, ctx):
        """Step 5b: bot has non-active items clogging inventory."""
        if not (not ctx.has_active and len(ctx.inv) >= MIN_INV_FOR_NONACTIVE_DELIVERY
                and self.active_on_shelves > 0 and len(self.bots) <= SMALL_TEAM_MAX):
            return False
        if ctx.pos == self.drop_off:
            self._emit(ctx.bid, ctx.bx, ctx.by, {"bot": ctx.bid, "action": "drop_off"})
            return True
        self._emit_move_or_wait(ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked)
        return True

    def _step_preview_prepick(self, ctx):
        """Step 6: pre-pick preview items."""
        # For 6+ bots: only force all slots when active items are done (avoid clog).
        # For smaller teams: always allow all slots (fewer bots = less clog risk).
        if len(self.bots) >= LARGE_TEAM_MIN:
            force = self.active_on_shelves == 0
        else:
            force = len(self.bots) >= SMALL_TEAM_MAX
        return self._try_preview_prepick(ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.inv, ctx.blocked,
                                         force_slots=force)

    def _step_clear_dropoff(self, ctx):
        """Step 7: clear dropoff area when idle."""
        return self._try_clear_dropoff(ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.blocked)

    def _step_idle_nonactive_deliver(self, ctx):
        """Step 7b: idle bot with non-active inventory -- deliver for points."""
        if not (ctx.inv and not ctx.has_active and len(ctx.inv) >= MIN_INV_FOR_NONACTIVE_DELIVERY):
            return False
        if ctx.pos == self.drop_off:
            self._emit(ctx.bid, ctx.bx, ctx.by, {"bot": ctx.bid, "action": "drop_off"})
            return True
        # Large teams: limit non-active deliverers to avoid dropoff congestion
        if len(self.bots) >= MEDIUM_TEAM_MIN and self._nonactive_delivering >= MAX_NONACTIVE_DELIVERERS:
            return False  # Fall through to idle positioning
        self._nonactive_delivering += 1
        self._emit_move_or_wait(ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked)
        return True

    def _step_idle_positioning(self, ctx):
        """Step 8: idle bot positioning -- spread out from other bots."""
        if len(self.bots) > 1:
            return self._try_idle_positioning(ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.blocked)
        return False

    # ------------------------------------------------------------------
    # Reusable item search helpers
    # ------------------------------------------------------------------

    def _is_available(self, item):
        """True if item is not claimed or blacklisted."""
        return item["id"] not in self.claimed and item["id"] not in self.gs.blacklisted_items

    def _iter_needed_items(self, needed):
        """Yield (item, is_cascade) for available items matching needed dict."""
        for item_type, count in needed.items():
            if count <= 0:
                continue
            is_cascade = item_type not in self.active_types
            for it in self.items_by_type.get(item_type, []):
                if self._is_available(it):
                    yield it, is_cascade

    def _find_adjacent_needed(self, bx, by, needed, prefer_cascade=False):
        """Find best needed item adjacent to (bx, by) using position lookup."""
        best = None
        best_cascade = False
        for dx, dy in DIRECTIONS:
            for it in self.items_at_pos.get((bx + dx, by + dy), []):
                if not self._is_available(it):
                    continue
                if needed.get(it["type"], 0) <= 0:
                    continue
                is_cascade = prefer_cascade and it["type"] not in self.active_types
                if is_cascade and not best_cascade:
                    best, best_cascade = it, True
                elif not best:
                    best = it
        return best

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _spare_slots(self, inv):
        return (MAX_INVENTORY - len(inv)) - self.active_on_shelves

    def _claim(self, item, needed_dict):
        self.claimed.add(item["id"])
        needed_dict[item["type"]] = needed_dict.get(item["type"], 0) - 1

    @staticmethod
    def _pickup(bid, item):
        return {"bot": bid, "action": "pick_up", "item_id": item["id"]}


# Populate the step chain after class definition so all methods exist.
RoundPlanner._STEP_CHAIN = [
    RoundPlanner._step_preview_bot,
    RoundPlanner._step_deliver_at_dropoff,
    RoundPlanner._step_deliver_completes_order,
    RoundPlanner._step_rush_deliver,
    RoundPlanner._step_opportunistic_preview,
    RoundPlanner._step_inventory_full_deliver,
    RoundPlanner._step_zero_cost_delivery,
    RoundPlanner._step_endgame,
    RoundPlanner._step_active_pickup,
    RoundPlanner._step_deliver_active,
    RoundPlanner._step_clear_nonactive_inventory,
    RoundPlanner._step_preview_prepick,
    RoundPlanner._step_clear_dropoff,
    RoundPlanner._step_idle_nonactive_deliver,
    RoundPlanner._step_idle_positioning,
]
