"""RoundPlanner — per-round decision orchestration for all bots."""

import math
from collections import deque, namedtuple
from typing import Any, Optional

from grocery_bot.pathfinding import DIRECTIONS
from grocery_bot.orders import get_needed_items

from grocery_bot.planner.movement import MovementMixin
from grocery_bot.planner.assignment import AssignmentMixin
from grocery_bot.planner.pickup import PickupMixin
from grocery_bot.planner.delivery import DeliveryMixin
from grocery_bot.planner.idle import IdleMixin
from grocery_bot.constants import (
    BOT_HISTORY_MAXLEN,
    DELIVER_WHEN_CLOSE_DIST,
    DELIVERY_QUEUE_TEAM_MIN,
    ENDGAME_ROUNDS_LEFT,
    LARGE_TEAM_MIN,
    MAX_CONCURRENT_DELIVERERS,
    MAX_INVENTORY,
    MAX_NONACTIVE_DELIVERERS,
    MEDIUM_TEAM_MIN,
    MIN_INV_FOR_NONACTIVE_DELIVERY,
    ORDER_NEARLY_COMPLETE_MAX,
    PICKUP_FAIL_BLACKLIST_THRESHOLD,
    PREDICTION_TEAM_MIN,
    SMALL_TEAM_MAX,
    TASK_COMMITMENT_ROUNDS,
)

# Bundles per-bot context passed through the step chain.
BotContext = namedtuple("BotContext", "bot bid bx by pos inv blocked has_active role")


def role_to_task_type(role: str) -> str:
    """Map a role name to its corresponding task type."""
    return {"pick": "pick", "deliver": "deliver", "preview": "preview"}.get(
        role, "idle"
    )


class RoundPlanner(
    MovementMixin, AssignmentMixin, PickupMixin, DeliveryMixin, IdleMixin
):
    """Plans actions for all bots in a single round.

    Encapsulates per-round mutable state (claims, predictions, net needs)
    and provides reusable methods for common item search patterns.
    """

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
        self.current_round: int = state["round"]
        self.rounds_left: int = state["max_rounds"] - state["round"]
        self.endgame: bool = self.rounds_left <= ENDGAME_ROUNDS_LEFT

        # Precomputed lookups
        self.bots_by_id: dict[int, dict[str, Any]] = {b["id"]: b for b in self.bots}
        self.items_at_pos: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for it in self.items:
            p = tuple(it["position"])
            self.items_at_pos.setdefault(p, []).append(it)

        # Per-round mutable state
        self.actions: list[dict[str, Any]] = []
        self.predicted: dict[int, tuple[int, int]] = {}  # bot_id -> predicted (x, y)
        self.claimed: set[str] = set()  # item IDs claimed this round
        self._yield_to: set[tuple[int, int]] = (
            set()
        )  # positions of higher-urgency bots to avoid
        self._nonactive_delivering: int = (
            0  # count of bots delivering non-active inventory
        )
        self._preview_walkers: int = (
            0  # count of non-preview bots walking to preview items
        )

    def plan(self) -> list[dict[str, Any]]:
        """Main entry: return list of action dicts for all bots."""
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

        self._detect_pickup_failures()

        if self.gs.blocked_static is None:
            self.gs.init_static({"grid": self._state_grid(), "items": self.items})

        self.active: Optional[dict[str, Any]] = next(
            (
                o
                for o in self.orders
                if o.get("status") == "active" and not o["complete"]
            ),
            None,
        )
        self.preview: Optional[dict[str, Any]] = next(
            (o for o in self.orders if o.get("status") == "preview"), None
        )

        if not self.active:
            return [{"bot": b["id"], "action": "wait"} for b in self.bots]

        # Detect order transitions and clear persistent state
        self._check_order_transition()

        self._compute_needs()
        self._compute_bot_assignments()

        # Coordination for large teams: delivery queue + roles
        self.bot_roles: dict[int, str] = {}
        self._use_coordination = len(self.bots) >= DELIVERY_QUEUE_TEAM_MIN
        if self._use_coordination:
            self._update_delivery_queue()
            self._assign_roles()
            self._update_persistent_tasks()

        self._pre_predict()

        urgency: dict[int, int] = {b["id"]: self._bot_urgency(b) for b in self.bots}
        self._decided: set[int] = set()  # bots whose actions are finalized

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
        """Extract grid from the state for init_static compatibility."""
        return self.full_state["grid"]

    # ------------------------------------------------------------------
    # Initialization helpers
    # ------------------------------------------------------------------

    def _detect_pickup_failures(self) -> None:
        gs = self.gs
        for b in self.bots:
            bid: int = b["id"]
            if bid not in gs.last_pickup:
                continue
            last_item_id, last_inv_len = gs.last_pickup[bid]
            if len(b["inventory"]) <= last_inv_len:
                gs.pickup_fail_count[last_item_id] = (
                    gs.pickup_fail_count.get(last_item_id, 0) + 1
                )
                if (
                    gs.pickup_fail_count[last_item_id]
                    >= PICKUP_FAIL_BLACKLIST_THRESHOLD
                ):
                    gs.blacklisted_items.add(last_item_id)
            else:
                gs.pickup_fail_count.pop(last_item_id, None)
            del gs.last_pickup[bid]

    def _compute_needs(self) -> None:
        self.active_needed: dict[str, int] = get_needed_items(self.active)
        preview_needed: dict[str, int] = (
            get_needed_items(self.preview) if self.preview else {}
        )

        self.items_by_type: dict[str, list[dict[str, Any]]] = {}
        for it in self.items:
            self.items_by_type.setdefault(it["type"], []).append(it)

        carried_active: dict[str, int] = {}
        carried_preview: dict[str, int] = {}
        self.bot_has_active: dict[int, bool] = {}
        self.bot_carried_active: dict[int, dict[str, int]] = {}
        for bot in self.bots:
            has = False
            bot_active: dict[str, int] = {}
            for inv_item in bot["inventory"]:
                if self.active_needed.get(inv_item, 0) > 0:
                    carried_active[inv_item] = carried_active.get(inv_item, 0) + 1
                    bot_active[inv_item] = bot_active.get(inv_item, 0) + 1
                    has = True
                elif inv_item in preview_needed:
                    carried_preview[inv_item] = carried_preview.get(inv_item, 0) + 1
            self.bot_has_active[bot["id"]] = has
            self.bot_carried_active[bot["id"]] = bot_active

        self.net_active: dict[str, int] = {
            t: c - carried_active.get(t, 0)
            for t, c in self.active_needed.items()
            if c - carried_active.get(t, 0) > 0
        }
        self.active_on_shelves: int = sum(self.net_active.values())

        self.net_preview: dict[str, int] = {
            t: c - carried_preview.get(t, 0)
            for t, c in preview_needed.items()
            if c - carried_preview.get(t, 0) > 0
        }
        self.active_types: set[str] = set(self.active_needed.keys())
        self.order_nearly_complete: bool = (
            0 < self.active_on_shelves <= ORDER_NEARLY_COMPLETE_MAX
        )

        idle_bots = sum(1 for bot in self.bots if not self._is_delivering(bot))
        total = self.active_on_shelves
        self.max_claim: int = (
            max(1, (total + idle_bots - 1) // idle_bots)
            if idle_bots > 0
            else MAX_INVENTORY
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

    # ------------------------------------------------------------------
    # Order transition detection (T15)
    # ------------------------------------------------------------------

    def _check_order_transition(self) -> None:
        """Detect when the active order changes and clear persistent state."""
        current_id = self.active["id"] if self.active else None
        if (
            self.gs.last_active_order_id is not None
            and current_id != self.gs.last_active_order_id
        ):
            # Order changed — clear all persistent coordination state
            self.gs.delivery_queue.clear()
            self.gs.bot_tasks.clear()
        self.gs.last_active_order_id = current_id

    # ------------------------------------------------------------------
    # Delivery queue management (T15)
    # ------------------------------------------------------------------

    def _update_delivery_queue(self) -> None:
        """Maintain the delivery queue for dropoff congestion control.

        A bot enters the queue when it has active items and either:
        - Its inventory is full, or
        - All its assigned items are picked (nothing left to pick)
        A bot leaves the queue when it no longer has active items (delivered).
        """
        gs = self.gs

        # Remove bots that no longer have active items or don't exist
        alive_ids = {b["id"] for b in self.bots}
        gs.delivery_queue = [
            bid
            for bid in gs.delivery_queue
            if bid in alive_ids and self.bot_has_active.get(bid, False)
        ]

        # Find bots that should be in the queue
        queue_set = set(gs.delivery_queue)
        new_candidates: list[tuple[float, int, int]] = []

        for bot in self.bots:
            bid = bot["id"]
            if bid in queue_set:
                continue
            if not self.bot_has_active.get(bid, False):
                continue

            inv = bot["inventory"]
            pos = tuple(bot["position"])

            # Should this bot join the queue?
            should_queue = False

            # Full inventory — must deliver
            if len(inv) >= MAX_INVENTORY:
                should_queue = True

            # All active items picked (nothing left on shelves for this bot)
            elif self.active_on_shelves == 0:
                should_queue = True

            # Bot has active items and no assigned items left to pick
            elif bid in self.bot_assignments and not self.bot_assignments[bid]:
                should_queue = True

            # Bot has active items and is not assigned anything
            elif bid not in self.bot_assignments and self.active_on_shelves == 0:
                should_queue = True

            if should_queue:
                d_to_drop = self.gs.dist_static(pos, self.drop_off)
                n_active = sum(
                    1 for item_type in inv if self.active_needed.get(item_type, 0) > 0
                )
                # Sort: closer to dropoff first, then more active items first
                new_candidates.append((d_to_drop, -n_active, bid))

        new_candidates.sort()
        for _, _, bid in new_candidates:
            gs.delivery_queue.append(bid)

    # ------------------------------------------------------------------
    # Role assignment (T15)
    # ------------------------------------------------------------------

    def _assign_roles(self) -> None:
        """Assign roles to bots based on game state.

        Roles: 'pick', 'deliver', 'preview', 'idle'
        """
        gs = self.gs
        num_bots = len(self.bots)

        # Determine how many active pickers we need
        if num_bots >= PREDICTION_TEAM_MIN:
            # Large teams: assign one picker per active item for faster collection
            active_picker_count = min(self.active_on_shelves, num_bots - 1)
        else:
            active_picker_count = math.ceil(self.active_on_shelves / MAX_INVENTORY)
            active_picker_count = (
                min(active_picker_count, num_bots - 1) if num_bots > 1 else num_bots
            )

        # Scale concurrent deliverers by team size
        if num_bots >= PREDICTION_TEAM_MIN:
            max_deliverers = max(2, num_bots // 4)
        elif num_bots >= MEDIUM_TEAM_MIN:
            max_deliverers = 2
        else:
            max_deliverers = MAX_CONCURRENT_DELIVERERS

        # Deliverer: first bots in the delivery queue
        delivering_count = 0
        for bid in gs.delivery_queue:
            if delivering_count >= max_deliverers:
                break
            self.bot_roles[bid] = "deliver"
            delivering_count += 1

        # Active pickers: bots with assigned items or closest to active items
        picker_candidates: list[tuple[float, int]] = []
        for bot in self.bots:
            bid = bot["id"]
            if bid in self.bot_roles:
                continue
            if self.bot_has_active.get(bid, False):
                # Bot already has active items but isn't in delivery queue
                # Likely still picking — keep as picker
                self.bot_roles[bid] = "pick"
                continue
            if bid in self.bot_assignments and self.bot_assignments[bid]:
                # Has assignments — is a picker
                pos = tuple(bot["position"])
                first_item = self.bot_assignments[bid][0]
                _, d = self.gs.find_best_item_target(pos, first_item)
                picker_candidates.append((d, bid))
            else:
                picker_candidates.append((float("inf"), bid))

        picker_candidates.sort()
        assigned_pickers = 0
        for _, bid in picker_candidates:
            if bid in self.bot_roles:
                continue
            if assigned_pickers < active_picker_count and self.active_on_shelves > 0:
                self.bot_roles[bid] = "pick"
                assigned_pickers += 1
            else:
                break

        # Preview pickers: use the existing preview_bot_ids from _assign_preview_bot
        # which are carefully chosen (furthest from active items)
        if self.preview and self.net_preview:
            for bid in self.preview_bot_ids:
                if bid not in self.bot_roles:
                    self.bot_roles[bid] = "preview"
            # For large teams with remaining unassigned bots, add more preview
            if num_bots >= 8:
                extra_preview = 0
                max_extra = max(0, min(2, num_bots) - len(self.preview_bot_ids))
                for bot in self.bots:
                    bid = bot["id"]
                    if bid in self.bot_roles:
                        continue
                    if extra_preview >= max_extra:
                        break
                    self.bot_roles[bid] = "preview"
                    self.preview_bot_ids.add(bid)
                    extra_preview += 1

        # Remaining bots: idle
        for bot in self.bots:
            bid = bot["id"]
            if bid not in self.bot_roles:
                self.bot_roles[bid] = "idle"

    # ------------------------------------------------------------------
    # Persistent task management (T15)
    # ------------------------------------------------------------------

    def _update_persistent_tasks(self) -> None:
        """Update persistent task assignments, respecting commitment periods."""
        gs = self.gs

        # Clean up completed/invalid tasks
        alive_ids = {b["id"] for b in self.bots}
        for bid in list(gs.bot_tasks.keys()):
            if bid not in alive_ids:
                del gs.bot_tasks[bid]
                continue

            task = gs.bot_tasks[bid]
            bot = self.bots_by_id.get(bid)
            if not bot:
                del gs.bot_tasks[bid]
                continue

            # Check if task is still valid
            if task["type"] == "pick":
                # Item still needed and available?
                target_type = task.get("item_type")
                if target_type and self.net_active.get(target_type, 0) <= 0:
                    del gs.bot_tasks[bid]
                    continue
                # Item blacklisted?
                item_id = task.get("item_id")
                if item_id and item_id in gs.blacklisted_items:
                    del gs.bot_tasks[bid]
                    continue

            elif task["type"] == "deliver":
                # Still has active items?
                if not self.bot_has_active.get(bid, False):
                    del gs.bot_tasks[bid]
                    continue

        # Assign new tasks for bots without valid ones
        for bot in self.bots:
            bid = bot["id"]
            role = self.bot_roles.get(bid, "idle")

            if bid in gs.bot_tasks:
                # Check commitment: don't reassign if still committed
                task = gs.bot_tasks[bid]
                if task.get("committed_until", 0) > self.current_round and task[
                    "type"
                ] == role_to_task_type(role):
                    continue

            # Assign based on role
            if role == "deliver":
                gs.bot_tasks[bid] = {
                    "type": "deliver",
                    "target": self.drop_off,
                    "committed_until": self.current_round + TASK_COMMITMENT_ROUNDS,
                }
            elif role == "pick":
                # Use bot_assignments if available
                if bid in self.bot_assignments and self.bot_assignments[bid]:
                    first_item = self.bot_assignments[bid][0]
                    gs.bot_tasks[bid] = {
                        "type": "pick",
                        "target": tuple(first_item["position"]),
                        "item_id": first_item["id"],
                        "item_type": first_item["type"],
                        "committed_until": self.current_round + TASK_COMMITMENT_ROUNDS,
                    }
                else:
                    gs.bot_tasks[bid] = {
                        "type": "pick",
                        "target": None,
                        "committed_until": self.current_round,
                    }
            elif role == "preview":
                gs.bot_tasks[bid] = {
                    "type": "preview",
                    "target": None,
                    "committed_until": self.current_round + TASK_COMMITMENT_ROUNDS,
                }
            else:
                gs.bot_tasks[bid] = {
                    "type": "idle",
                    "target": None,
                    "committed_until": self.current_round,
                }

    # ------------------------------------------------------------------
    # Per-bot decision (steps 1-8)
    # ------------------------------------------------------------------

    # Step chain: each method returns True if it handled the bot.
    _STEP_CHAIN: Optional[list] = None  # populated after class definition

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
            bot=bot,
            bid=bid,
            bx=bx,
            by=by,
            pos=(bx, by),
            inv=bot["inventory"],
            blocked=self._build_blocked(bid),
            has_active=self.bot_has_active[bid],
            role=self.bot_roles.get(bid, "pick"),
        )

    # ------------------------------------------------------------------
    # Individual decision steps
    # ------------------------------------------------------------------

    def _step_preview_bot(self, ctx: BotContext) -> bool:
        """Phase 2.2: dedicated preview bot skips active items entirely."""
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

    def _step_deliver_at_dropoff(self, ctx: BotContext) -> bool:
        """Step 1: at drop-off with active items -> deliver."""
        if ctx.pos == self.drop_off and ctx.has_active:
            self._emit(ctx.bid, ctx.bx, ctx.by, {"bot": ctx.bid, "action": "drop_off"})
            return True
        return False

    def _step_deliver_completes_order(self, ctx: BotContext) -> bool:
        """Phase 4.4: deliver partial items if it COMPLETES the order (+5 bonus)."""
        if (
            ctx.has_active
            and self.active_on_shelves > 0
            and len(ctx.inv) < MAX_INVENTORY
            and self._bot_delivery_completes_order(ctx.bot)
        ):
            self._emit_move_or_wait(
                ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked
            )
            return True
        return False

    def _step_rush_deliver(self, ctx: BotContext) -> bool:
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
        self._emit_move_or_wait(
            ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked
        )
        return True

    def _step_opportunistic_preview(self, ctx: BotContext) -> bool:
        """Step 3: opportunistic adjacent preview pickup (spare slots only)."""
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

    def _step_inventory_full_deliver(self, ctx: BotContext) -> bool:
        """Step 3b: inventory full -> deliver."""
        if not (ctx.has_active and len(ctx.inv) >= MAX_INVENTORY):
            return False
        self._emit_move_or_wait(
            ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked
        )
        return True

    def _step_zero_cost_delivery(self, ctx: BotContext) -> bool:
        """Phase 4.4: zero-cost delivery -- deliver if adjacent to dropoff."""
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
                self._emit_move_or_wait(
                    ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked
                )
                return True
        return False

    def _step_endgame(self, ctx: BotContext) -> bool:
        """Phase 4.3: improved end-game strategy."""
        if not (self.endgame and ctx.inv):
            return False
        d = self.gs.dist_static(ctx.pos, self.drop_off)
        if d + 1 >= self.rounds_left:
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

    def _step_active_pickup(self, ctx: BotContext) -> bool:
        """Step 4: pick up active items (adjacent first, then TSP route)."""
        return self._try_active_pickup(
            ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.inv, ctx.blocked
        )

    def _step_deliver_active(self, ctx: BotContext) -> bool:
        """Step 5: deliver active items."""
        if not ctx.has_active:
            return False
        d_to_drop = self.gs.dist_static(ctx.pos, self.drop_off)
        if (
            self.active_on_shelves > 0
            and len(ctx.inv) >= 2
            and d_to_drop <= DELIVER_WHEN_CLOSE_DIST
        ):
            self._emit_move_or_wait(
                ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked
            )
            return True

        spare = self._spare_slots(ctx.inv)
        if self.preview and spare > 0 and not self.order_nearly_complete:
            item, cell = self._find_detour_item(ctx.pos, self.net_preview)
            if item:
                self._claim(item, self.net_preview)
                if self._emit_move(ctx.bid, ctx.bx, ctx.by, ctx.pos, cell, ctx.blocked):
                    return True
        self._emit_move_or_wait(
            ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked
        )
        return True

    def _step_clear_nonactive_inventory(self, ctx: BotContext) -> bool:
        """Step 5b: bot has non-active items clogging inventory."""
        if ctx.has_active or len(ctx.inv) == 0 or self.active_on_shelves == 0:
            return False

        num_bots = len(self.bots)
        # Small teams (<=3): clear if holding 2+ non-active items
        # Medium teams (4-7): clear only when inventory is completely full
        # Large teams (8+): skip — dropoff congestion outweighs benefit
        if num_bots <= SMALL_TEAM_MAX:
            if len(ctx.inv) < MIN_INV_FOR_NONACTIVE_DELIVERY:
                return False
        elif num_bots < PREDICTION_TEAM_MIN:
            if len(ctx.inv) < MAX_INVENTORY:
                return False
        else:
            return False

        if ctx.pos == self.drop_off:
            self._emit(ctx.bid, ctx.bx, ctx.by, {"bot": ctx.bid, "action": "drop_off"})
            return True
        # Limit non-active deliverers on medium+ teams to avoid congestion
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

    def _step_preview_prepick(self, ctx: BotContext) -> bool:
        """Step 6: pre-pick preview items."""
        # For 6+ bots: only force all slots when active items are done (avoid clog).
        # For medium teams (3-5 bots): only force when active items nearly done,
        # to avoid filling inventory with preview items that may not match next order.
        num_bots = len(self.bots)
        if num_bots >= LARGE_TEAM_MIN:
            force = self.active_on_shelves == 0
        elif num_bots >= SMALL_TEAM_MAX:
            force = self.active_on_shelves <= 1
        else:
            force = False
        return self._try_preview_prepick(
            ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.inv, ctx.blocked, force_slots=force
        )

    def _step_clear_dropoff(self, ctx: BotContext) -> bool:
        """Step 7: clear dropoff area when idle."""
        return self._try_clear_dropoff(ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.blocked)

    def _step_idle_nonactive_deliver(self, ctx: BotContext) -> bool:
        """Step 7b: idle bot with non-active inventory -- deliver for points."""
        if not (
            ctx.inv
            and not ctx.has_active
            and len(ctx.inv) >= MIN_INV_FOR_NONACTIVE_DELIVERY
        ):
            return False
        if ctx.pos == self.drop_off:
            self._emit(ctx.bid, ctx.bx, ctx.by, {"bot": ctx.bid, "action": "drop_off"})
            return True
        # Large teams: limit non-active deliverers to avoid dropoff congestion
        if (
            len(self.bots) >= MEDIUM_TEAM_MIN
            and self._nonactive_delivering >= MAX_NONACTIVE_DELIVERERS
        ):
            return False  # Fall through to idle positioning
        self._nonactive_delivering += 1
        self._emit_move_or_wait(
            ctx.bid, ctx.bx, ctx.by, ctx.pos, self.drop_off, ctx.blocked
        )
        return True

    def _step_idle_positioning(self, ctx: BotContext) -> bool:
        """Step 8: idle bot positioning -- spread out from other bots."""
        if len(self.bots) > 1:
            return self._try_idle_positioning(
                ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.blocked
            )
        return False

    # ------------------------------------------------------------------
    # Reusable item search helpers
    # ------------------------------------------------------------------

    def _is_available(self, item: dict[str, Any]) -> bool:
        """True if item is not claimed or blacklisted."""
        return (
            item["id"] not in self.claimed
            and item["id"] not in self.gs.blacklisted_items
        )

    def _iter_needed_items(self, needed: dict[str, int]):
        """Yield (item, is_cascade) for available items matching needed dict."""
        for item_type, count in needed.items():
            if count <= 0:
                continue
            is_cascade = item_type not in self.active_types
            for it in self.items_by_type.get(item_type, []):
                if self._is_available(it):
                    yield it, is_cascade

    def _find_adjacent_needed(
        self,
        bx: int,
        by: int,
        needed: dict[str, int],
        prefer_cascade: bool = False,
    ) -> Optional[dict[str, Any]]:
        """Find best needed item adjacent to (bx, by) using position lookup."""
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

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _spare_slots(self, inv: list[str]) -> int:
        return (MAX_INVENTORY - len(inv)) - self.active_on_shelves

    def _claim(self, item: dict[str, Any], needed_dict: dict[str, int]) -> None:
        self.claimed.add(item["id"])
        needed_dict[item["type"]] = needed_dict.get(item["type"], 0) - 1

    @staticmethod
    def _pickup(bid: int, item: dict[str, Any]) -> dict[str, Any]:
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
