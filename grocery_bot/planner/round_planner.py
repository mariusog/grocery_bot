"""RoundPlanner — per-round decision orchestration for all bots."""

from collections import deque, namedtuple
from typing import Any, Optional

from grocery_bot.orders import get_needed_items
from grocery_bot.constants import (
    BLACKLIST_EXPIRY_ROUNDS,
    BOT_HISTORY_MAXLEN,
    DELIVERY_QUEUE_TEAM_MIN,
    DROPOFF_CLEAR_RADIUS,
    ENDGAME_ROUNDS_LEFT,
    MAX_INVENTORY,
    ORDER_NEARLY_COMPLETE_MAX,
    PICKUP_FAIL_BLACKLIST_THRESHOLD,
    ZONE_CONGESTION_WEIGHT,
)

from grocery_bot.planner.movement import MovementMixin
from grocery_bot.planner.assignment import AssignmentMixin
from grocery_bot.planner.pickup import PickupMixin
from grocery_bot.planner.preview import PreviewMixin
from grocery_bot.planner.delivery import DeliveryMixin
from grocery_bot.planner.idle import IdleMixin
from grocery_bot.planner.speculative import SpeculativeMixin
from grocery_bot.planner.spawn import SpawnMixin
from grocery_bot.planner.coordination import CoordinationMixin
from grocery_bot.planner.steps import StepsMixin

# Bundles per-bot context passed through the step chain.
BotContext = namedtuple("BotContext", "bot bid bx by pos inv blocked has_active role")


class RoundPlanner(
    MovementMixin, AssignmentMixin, PickupMixin, PreviewMixin, DeliveryMixin,
    IdleMixin, SpeculativeMixin, SpawnMixin, CoordinationMixin, StepsMixin,
):
    """Plans actions for all bots in a single round."""

    # Step chain: populated after class definition.
    _STEP_CHAIN: Optional[list] = None

    def __init__(
        self,
        gs: Any,
        state: dict[str, Any],
        full_state: Optional[dict[str, Any]] = None,
    ) -> None:
        self.gs = gs
        self.full_state: dict[str, Any] = (
            full_state if full_state is not None else state
        )
        self.bots: list[dict[str, Any]] = state["bots"]
        self.items: list[dict[str, Any]] = state["items"]
        self.orders: list[dict[str, Any]] = state["orders"]
        self.drop_off: tuple[int, int] = tuple(state["drop_off"])
        zones = state.get("drop_off_zones")
        self.drop_off_zones: list[tuple[int, int]] = (
            [tuple(z) for z in zones] if zones else [self.drop_off]
        )
        self.current_round: int = state["round"]
        self.rounds_left: int = state["max_rounds"] - state["round"]
        self.endgame: bool = self.rounds_left <= ENDGAME_ROUNDS_LEFT

        self.bots_by_id: dict[int, dict[str, Any]] = {b["id"]: b for b in self.bots}
        self.items_at_pos: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for it in self.items:
            p = tuple(it["position"])
            self.items_at_pos.setdefault(p, []).append(it)

        # Per-round mutable state
        self.actions: list[dict[str, Any]] = []
        self.predicted: dict[int, tuple[int, int]] = {}
        self.claimed: set[str] = set()
        self._yield_to: set[tuple[int, int]] = set()
        self._nonactive_delivering: int = 0
        self._preview_walkers: int = 0
        self._speculative_pickers: int = 0
        self._spec_types_claimed: set[str] = set()
        self.spec_assignments: dict[int, dict[str, Any]] = {}

    def plan(self) -> list[dict[str, Any]]:
        """Main entry: return list of action dicts for all bots."""
        self.gs.last_round_processed = self.full_state.get("round", -1)
        self._init_bot_history()
        self._detect_pickup_failures()
        self._expire_blacklists()

        if self.gs.blocked_static is None:
            self.gs.init_static({
                "grid": self._state_grid(),
                "items": self.items,
                "drop_off": list(self.drop_off),
            })

        self.active: Optional[dict[str, Any]] = next(
            (o for o in self.orders
             if o.get("status") == "active" and not o["complete"]),
            None,
        )
        self.preview: Optional[dict[str, Any]] = next(
            (o for o in self.orders if o.get("status") == "preview"), None
        )

        if not self.active:
            return [{"bot": b["id"], "action": "wait"} for b in self.bots]

        self._check_order_transition()
        self._compute_needs()
        self._compute_bot_assignments()
        self._assign_speculative_targets()
        self.gs.update_round_positions(
            {b["id"]: tuple(b["position"]) for b in self.bots},
            self.drop_off,
        )

        self.bot_roles: dict[int, str] = {}
        self._use_coordination = len(self.bots) >= DELIVERY_QUEUE_TEAM_MIN
        if self._use_coordination:
            self._update_delivery_queue()
            self._assign_roles()
            self._update_persistent_tasks()

        self._pre_predict()

        urgency: dict[int, int] = {b["id"]: self._bot_urgency(b) for b in self.bots}
        self._decided: set[int] = set()

        for bot in self.bots:
            bid = bot["id"]
            self._yield_to = set()
            for b in self.bots:
                if b["id"] == bid or b["id"] in self._decided:
                    continue
                if urgency[b["id"]] < urgency[bid]:
                    self._yield_to.add(tuple(b["position"]))
            self._decide_bot(bot)

        return self.actions

    def _state_grid(self) -> dict[str, Any]:
        return self.full_state["grid"]

    def _init_bot_history(self) -> None:
        """Initialize or validate bot history tracking."""
        gen = id(self.gs.dist_cache)
        needs_reset = (
            not hasattr(self.gs, "bot_history")
            or not hasattr(self.gs, "_history_gen")
            or self.gs._history_gen != gen
        )
        if needs_reset:
            self.gs.bot_history = {}
            self.gs._history_gen = gen

        for b in self.bots:
            bid: int = b["id"]
            pos: tuple[int, int] = tuple(b["position"])
            if bid not in self.gs.bot_history:
                self.gs.bot_history[bid] = deque(maxlen=BOT_HISTORY_MAXLEN)
            self.gs.bot_history[bid].append(pos)

    def _detect_pickup_failures(self) -> None:
        gs = self.gs
        for b in self.bots:
            bid: int = b["id"]
            if bid not in gs.last_pickup:
                continue
            last_item_id, last_inv_len = gs.last_pickup[bid]
            actual_pos = tuple(b["position"])

            # Check if bot is at the expected position — if not, this is a
            # desync (server didn't apply our action) and we should NOT count
            # the pickup failure.
            expected_pos = gs.last_expected_pos.get(bid)
            position_matches = expected_pos is None or actual_pos == expected_pos

            if len(b["inventory"]) <= last_inv_len:
                if position_matches:
                    gs.pickup_fail_count[last_item_id] = (
                        gs.pickup_fail_count.get(last_item_id, 0) + 1
                    )
                    if (
                        gs.pickup_fail_count[last_item_id]
                        >= PICKUP_FAIL_BLACKLIST_THRESHOLD
                    ):
                        gs.blacklisted_items.add(last_item_id)
                        current_round = self.full_state.get("round", 0)
                        gs.blacklist_round[last_item_id] = current_round
                # else: desync detected, don't count failure
            else:
                gs.pickup_fail_count.pop(last_item_id, None)
            del gs.last_pickup[bid]

    def _expire_blacklists(self) -> None:
        """Remove blacklisted items whose expiry window has passed."""
        gs = self.gs
        current_round = self.full_state.get("round", 0)
        expired = [
            item_id
            for item_id, bl_round in gs.blacklist_round.items()
            if current_round - bl_round >= BLACKLIST_EXPIRY_ROUNDS
        ]
        for item_id in expired:
            gs.blacklisted_items.discard(item_id)
            del gs.blacklist_round[item_id]
            gs.pickup_fail_count.pop(item_id, None)

    def _count_usable_inventory(
        self,
        bot: dict[str, Any],
        remaining: dict[str, int],
        reserved: Optional[dict[str, int]] = None,
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
        reserved_by_bot: Optional[dict[int, dict[str, int]]] = None,
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
        allocated_by_bot: dict[int, dict[str, int]] = {
            b["id"]: {} for b in self.bots
        }
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
                ranked.append(
                    (-useful_types, d_to_drop, -useful_total, bot["id"], bot)
                )

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

    def _compute_needs(self) -> None:
        self.active_needed: dict[str, int] = get_needed_items(self.active)
        preview_needed = get_needed_items(self.preview) if self.preview else {}
        self.items_by_type: dict[str, list[dict[str, Any]]] = {}
        for it in self.items:
            self.items_by_type.setdefault(it["type"], []).append(it)
        _, self.bot_carried_active, self.net_active = self._allocate_carried_need(
            self.active_needed
        )
        self.bot_has_active = {
            bid: bool(bot_active)
            for bid, bot_active in self.bot_carried_active.items()
        }
        self.active_on_shelves: int = sum(self.net_active.values())
        _, _, self.net_preview = self._allocate_carried_need(
            preview_needed, reserved_by_bot=self.bot_carried_active
        )
        self.active_types: set[str] = set(self.active_needed.keys())
        self.order_nearly_complete: bool = (
            0 < self.active_on_shelves <= ORDER_NEARLY_COMPLETE_MAX
        )
        idle_bots = sum(1 for bot in self.bots if not self._is_delivering(bot))
        total = self.active_on_shelves
        self.max_claim: int = (
            max(1, (total + idle_bots - 1) // idle_bots)
            if idle_bots > 0 else MAX_INVENTORY
        )
        self.num_item_types: int = len(self.items_by_type)
        self.preview_bot_id: Optional[int] = None
        self.preview_bot_ids: set[int] = set()
        if (
            self.order_nearly_complete
            and len(self.bots) >= 2
            and self.preview
            and self.net_preview
        ):
            self._assign_preview_bot()

    def _decide_bot(self, bot: dict[str, Any]) -> None:
        ctx = self._build_bot_context(bot)
        for step in self._STEP_CHAIN:
            if step(self, ctx):
                return
        self._emit(ctx.bid, ctx.bx, ctx.by, {"bot": ctx.bid, "action": "wait"})

    def _build_bot_context(self, bot: dict[str, Any]) -> BotContext:
        bid: int = bot["id"]
        bx, by = bot["position"]
        return BotContext(
            bot=bot, bid=bid, bx=bx, by=by, pos=(bx, by),
            inv=bot["inventory"],
            blocked=self._build_blocked(bid),
            has_active=self.bot_has_active[bid],
            role=self.bot_roles.get(bid, "pick"),
        )

    def _is_available(self, item: dict[str, Any]) -> bool:
        return (
            item["id"] not in self.claimed
            and item["id"] not in self.gs.blacklisted_items
        )

    def _iter_needed_items(self, needed: dict[str, int]):
        for item_type, count in needed.items():
            if count <= 0:
                continue
            is_cascade = item_type not in self.active_types
            for it in self.items_by_type.get(item_type, []):
                if self._is_available(it):
                    yield it, is_cascade

    def _find_adjacent_needed(
        self, bx: int, by: int, needed: dict[str, int],
        prefer_cascade: bool = False,
    ) -> Optional[dict[str, Any]]:
        from grocery_bot.pathfinding import DIRECTIONS
        best: Optional[dict[str, Any]] = None
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

    def _nearest_dropoff(self, pos: tuple[int, int]) -> tuple[int, int]:
        """Return the best drop-off zone considering distance and congestion."""
        if len(self.drop_off_zones) == 1:
            return self.drop_off_zones[0]
        best = self.drop_off_zones[0]
        best_score = self.gs.dist_static(pos, best) + self._zone_congestion(best)
        for zone in self.drop_off_zones[1:]:
            score = self.gs.dist_static(pos, zone) + self._zone_congestion(zone)
            if score < best_score:
                best, best_score = zone, score
        return best

    def _zone_congestion(self, zone: tuple[int, int]) -> float:
        """Estimate congestion penalty near a drop zone (idle bots nearby)."""
        count = 0
        for b in self.bots:
            bpos = tuple(b["position"])
            if bpos == zone:
                continue
            d = abs(bpos[0] - zone[0]) + abs(bpos[1] - zone[1])
            if d <= DROPOFF_CLEAR_RADIUS:
                count += 1
        return count * ZONE_CONGESTION_WEIGHT

    def _is_at_any_dropoff(self, pos: tuple[int, int]) -> bool:
        """Return True if *pos* is any of the drop-off zones."""
        return pos in self.drop_off_zones

    def _spare_slots(self, inv: list[str], bid: int = -1) -> int:
        if bid >= 0 and len(self.bots) >= 2 and hasattr(self, 'bot_assignments'):
            my_assigned = len(self.bot_assignments.get(bid, []))
            reserve = min(self.active_on_shelves, my_assigned)
        else:
            reserve = self.active_on_shelves
        return (MAX_INVENTORY - len(inv)) - reserve

    def _claim(self, item: dict[str, Any], needed_dict: dict[str, int]) -> None:
        self.claimed.add(item["id"])
        needed_dict[item["type"]] = needed_dict.get(item["type"], 0) - 1

    @staticmethod
    def _pickup(bid: int, item: dict[str, Any]) -> dict[str, Any]:
        return {"bot": bid, "action": "pick_up", "item_id": item["id"]}


# Populate the step chain after class definition.
RoundPlanner._STEP_CHAIN = [
    RoundPlanner._step_spawn_dispersal,
    RoundPlanner._step_preview_bot,
    RoundPlanner._step_deliver_at_dropoff,
    RoundPlanner._step_deliver_completes_order,
    RoundPlanner._step_rush_deliver,
    RoundPlanner._step_opportunistic_preview,
    RoundPlanner._step_inventory_full_deliver,
    RoundPlanner._step_zero_cost_delivery,
    RoundPlanner._step_early_delivery,
    RoundPlanner._step_endgame,
    RoundPlanner._step_active_pickup,
    RoundPlanner._step_deliver_active,
    RoundPlanner._step_clear_nonactive_inventory,
    RoundPlanner._step_preview_prepick,
    RoundPlanner._step_speculative_pickup,
    RoundPlanner._step_break_oscillation,
    RoundPlanner._step_clear_dropoff,
    RoundPlanner._step_idle_nonactive_deliver,
    RoundPlanner._step_idle_positioning,
]
