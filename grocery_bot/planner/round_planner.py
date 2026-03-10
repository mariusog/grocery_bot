"""RoundPlanner — per-round decision orchestration for all bots."""

from collections import namedtuple
from collections.abc import Iterator
from typing import Any

from grocery_bot.constants import (
    DROPOFF_CLEAR_RADIUS,
    ENDGAME_ROUNDS_LEFT,
    MAX_INVENTORY,
    ORDER_NEARLY_COMPLETE_MAX,
    ZONE_CONGESTION_WEIGHT,
)
from grocery_bot.orders import get_needed_items
from grocery_bot.planner.assignment import AssignmentMixin
from grocery_bot.planner.blacklist import BlacklistMixin
from grocery_bot.planner.coordination import CoordinationMixin
from grocery_bot.planner.delivery import DeliveryMixin
from grocery_bot.planner.idle import IdleMixin
from grocery_bot.planner.inventory import InventoryMixin
from grocery_bot.planner.movement import MovementMixin
from grocery_bot.planner.pickup import PickupMixin
from grocery_bot.planner.preview import PreviewMixin
from grocery_bot.planner.spawn import SpawnMixin
from grocery_bot.planner.speculative import SpeculativeMixin
from grocery_bot.planner.steps import StepsMixin
from grocery_bot.team_config import TeamConfig, get_team_config

# Bundles per-bot context passed through the step chain.
BotContext = namedtuple("BotContext", "bot bid bx by pos inv blocked has_active role")


class RoundPlanner(
    MovementMixin,
    AssignmentMixin,
    BlacklistMixin,
    InventoryMixin,
    PickupMixin,
    PreviewMixin,
    DeliveryMixin,
    IdleMixin,
    SpeculativeMixin,
    SpawnMixin,
    CoordinationMixin,
    StepsMixin,
):
    """Plans actions for all bots in a single round."""

    # Step chain: populated after class definition.
    _STEP_CHAIN: list | None = None

    def __init__(
        self,
        gs: Any,
        state: dict[str, Any],
        full_state: dict[str, Any] | None = None,
    ) -> None:
        self.gs = gs
        self.full_state: dict[str, Any] = full_state if full_state is not None else state
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

        self.cfg: TeamConfig = get_team_config(len(self.bots))
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

        if not self.gs.blocked_static:
            self.gs.init_static(
                {
                    "grid": self._state_grid(),
                    "items": self.items,
                    "drop_off": list(self.drop_off),
                }
            )

        self.active: dict[str, Any] | None = next(
            (o for o in self.orders if o.get("status") == "active" and not o["complete"]),
            None,
        )
        self.preview: dict[str, Any] | None = next(
            (o for o in self.orders if o.get("status") == "preview"), None
        )

        if not self.active:
            return [{"bot": b["id"], "action": "wait"} for b in self.bots]

        self._check_order_transition()
        self._compute_needs()
        self._compute_bot_assignments()
        self._identify_batch_b()
        self._assign_speculative_targets()
        self.gs.update_round_positions(
            {b["id"]: tuple(b["position"]) for b in self.bots},
            self.drop_off,
        )

        self.bot_roles: dict[int, str] = {}
        self._use_coordination = self.cfg.use_coordination
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
        grid: dict[str, Any] = self.full_state["grid"]
        return grid

    def _compute_needs(self) -> None:
        assert self.active is not None, "_compute_needs called with no active order"
        self.active_needed: dict[str, int] = get_needed_items(self.active)
        preview_needed = get_needed_items(self.preview) if self.preview else {}
        self.items_by_type: dict[str, list[dict[str, Any]]] = {}
        for it in self.items:
            self.items_by_type.setdefault(it["type"], []).append(it)
        _, self.bot_carried_active, self.net_active = self._allocate_carried_need(
            self.active_needed
        )
        self.bot_has_active = {
            bid: bool(bot_active) for bid, bot_active in self.bot_carried_active.items()
        }
        self.active_on_shelves: int = sum(self.net_active.values())
        _, _, self.net_preview = self._allocate_carried_need(
            preview_needed, reserved_by_bot=self.bot_carried_active
        )
        preview_on_shelves: int = sum(self.net_preview.values())
        self.wave_mode: bool = self.cfg.use_wave_mode and self.preview is not None
        self.wave_on_shelves: int = (
            self.active_on_shelves + preview_on_shelves if self.wave_mode else -1
        )
        self.batch_b_bots: set[int] = set()
        self.active_types: set[str] = set(self.active_needed.keys())
        self.order_nearly_complete: bool = 0 < self.active_on_shelves <= ORDER_NEARLY_COMPLETE_MAX
        idle_bots = sum(1 for bot in self.bots if not self._is_delivering(bot))
        total = self.active_on_shelves
        self.max_claim: int = (
            max(1, (total + idle_bots - 1) // idle_bots) if idle_bots > 0 else MAX_INVENTORY
        )
        self.num_item_types: int = len(self.items_by_type)
        self.preview_bot_id: int | None = None
        self.preview_bot_ids: set[int] = set()
        if self.order_nearly_complete and len(self.bots) >= 2 and self.preview and self.net_preview:
            self._assign_preview_bot()

    def _decide_bot(self, bot: dict[str, Any]) -> None:
        ctx = self._build_bot_context(bot)
        assert self._STEP_CHAIN is not None
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

    def _is_available(self, item: dict[str, Any]) -> bool:
        return item["id"] not in self.claimed and item["id"] not in self.gs.blacklisted_items

    def _iter_needed_items(self, needed: dict[str, int]) -> Iterator[tuple[dict[str, Any], bool]]:
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
    ) -> dict[str, Any] | None:
        from grocery_bot.pathfinding import DIRECTIONS

        best: dict[str, Any] | None = None
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
        if bid >= 0 and len(self.bots) >= 2 and hasattr(self, "bot_assignments"):
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
    RoundPlanner._step_wave_rush_deliver,
    RoundPlanner._step_early_delivery,
    RoundPlanner._step_opportunistic_preview,
    RoundPlanner._step_inventory_full_deliver,
    RoundPlanner._step_zero_cost_delivery,
    RoundPlanner._step_endgame,
    RoundPlanner._step_batch_b_preview,
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
