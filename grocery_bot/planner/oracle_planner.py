"""OraclePlanner — per-round action executor using a pre-built schedule.

Translates the OracleScheduler's global plan into concrete per-round
actions for each bot. Replans on order transitions, stuck bots, and
schedule exhaustion.
"""

from __future__ import annotations

from typing import Any

from grocery_bot.constants import (
    MAX_INVENTORY,
    ORACLE_REPLAN_INTERVAL,
    ORACLE_STUCK_THRESHOLD,
)
from grocery_bot.pathfinding import DIRECTIONS, bfs
from grocery_bot.planner.oracle_scheduler import OracleScheduler
from grocery_bot.planner.oracle_types import Schedule


class OraclePlanner:
    """Per-round planner that executes a pre-built oracle schedule."""

    def __init__(
        self,
        gs: Any,
        state: dict[str, Any],
        full_state: dict[str, Any] | None = None,
    ) -> None:
        self.gs = gs
        self.state = state
        self.full_state = full_state or state
        self.bots: list[dict[str, Any]] = state["bots"]
        self.items: list[dict[str, Any]] = state["items"]
        self.orders: list[dict[str, Any]] = state["orders"]
        self.drop_off: tuple[int, int] = tuple(state["drop_off"])
        zones = state.get("drop_off_zones")
        self.drop_off_zones: list[tuple[int, int]] = (
            [tuple(z) for z in zones] if zones else [self.drop_off]
        )
        self.current_round: int = state["round"]
        self.max_rounds: int = state["max_rounds"]
        self._active_idx: int = state.get("active_order_index", 0)

        self._items_by_id: dict[str, dict[str, Any]] = {it["id"]: it for it in self.items}
        self._items_at_pos: dict[tuple[int, int], list[dict[str, Any]]] = {}
        for it in self.items:
            p = tuple(it["position"])
            self._items_at_pos.setdefault(p, []).append(it)
        self._bot_positions: dict[int, tuple[int, int]] = {
            b["id"]: tuple(b["position"]) for b in self.bots
        }
        self._bot_inventories: dict[int, list[str]] = {
            b["id"]: list(b["inventory"]) for b in self.bots
        }

    def plan(self) -> list[dict[str, Any]]:
        """Generate actions for all bots this round."""
        schedule = self._get_or_build_schedule()
        active = self._get_active_order()
        if not active:
            return [{"bot": b["id"], "action": "wait"} for b in self.bots]

        active_needed = self._get_active_needed(active)
        self._detect_stuck_bots(schedule)

        actions: list[dict[str, Any]] = []
        # Track decided bot destinations (for collision avoidance)
        decided_dests: set[tuple[int, int]] = set()
        decided_bids: set[int] = set()
        claimed_items: set[str] = set()

        # Sort bots: those carrying active items first (urgency ordering)
        sorted_bots = sorted(
            self.bots,
            key=lambda b: -self._count_active(self._bot_inventories[b["id"]], active_needed),
        )
        for bot in sorted_bots:
            bid = bot["id"]
            pos = self._bot_positions[bid]
            inv = self._bot_inventories[bid]
            # Build blocked set: decided bots' destinations + undecided bots' positions
            blocked_dynamic = self._build_dynamic_blocked(bid, decided_dests, decided_bids)
            action = self._decide_bot(
                bid,
                pos,
                inv,
                schedule,
                active_needed,
                blocked_dynamic,
                decided_dests,
                claimed_items,
            )
            actions.append(action)
            dest = self._action_destination(pos, action)
            decided_dests.add(dest)
            decided_bids.add(bid)
            if action.get("item_id"):
                claimed_items.add(action["item_id"])

        return actions

    def _build_dynamic_blocked(
        self,
        bid: int,
        decided_dests: set[tuple[int, int]],
        decided_bids: set[int],
    ) -> set[tuple[int, int]]:
        """Build collision set: decided destinations + undecided positions."""
        blocked = set(decided_dests)
        for other_bid, other_pos in self._bot_positions.items():
            if other_bid != bid and other_bid not in decided_bids:
                blocked.add(other_pos)
        return blocked

    def _decide_bot(
        self,
        bid: int,
        pos: tuple[int, int],
        inv: list[str],
        schedule: Schedule,
        active_needed: dict[str, int],
        blocked_dynamic: set[tuple[int, int]],
        decided_dests: set[tuple[int, int]],
        claimed_items: set[str],
    ) -> dict[str, Any]:
        """Decide action for a single bot using the schedule."""
        active_count = self._count_active(inv, active_needed)
        inv_full = len(inv) >= MAX_INVENTORY

        # P1: At dropoff with active items → drop_off
        if self._is_at_dropoff(pos) and active_count > 0:
            return {"bot": bid, "action": "drop_off"}

        # P2: Inventory full → deliver what we have
        if inv_full and active_count > 0:
            return self._move_toward(bid, pos, self._nearest_drop(pos), blocked_dynamic)

        # P3: Adjacent to scheduled pickup → pick_up (if still needed)
        task = schedule.peek_task(bid)
        if task and task.is_pickup() and not inv_full:
            item = self._items_by_id.get(task.item_id or "")
            if item and self._is_adjacent(pos, tuple(item["position"])):
                itype = item["type"]
                remaining = dict(active_needed)
                for t in inv:
                    if remaining.get(t, 0) > 0:
                        remaining[t] -= 1
                if remaining.get(itype, 0) > 0:
                    schedule.pop_task(bid)
                    return _pickup_action(bid, item["id"])
                else:
                    schedule.pop_task(bid)  # Skip unneeded pickup

        # P4: Adjacent to needed item (opportunistic, budget-aware)
        if not inv_full:
            adj_item = self._find_adjacent_needed(pos, active_needed, inv, claimed_items)
            if adj_item:
                schedule.pop_matching_pickup(bid, adj_item["id"])
                return _pickup_action(bid, adj_item["id"])

        # P5: Has active items + no more pickups → deliver
        if active_count > 0 and not self._has_pending_picks(bid, schedule):
            return self._move_toward(bid, pos, self._nearest_drop(pos), blocked_dynamic)

        # P6: Has scheduled pickup → move toward it (re-peek after P3 skip)
        task = schedule.peek_task(bid)
        if task and task.is_pickup() and not inv_full:
            item = self._items_by_id.get(task.item_id or "")
            if not item:
                schedule.pop_task(bid)
                return self._fallback(bid, pos, active_count, blocked_dynamic)
            return self._move_toward(bid, pos, task.target_pos, blocked_dynamic)

        # P7: Inventory full with pending picks → skip picks, deliver
        if inv_full and self._has_pending_picks(bid, schedule):
            self._skip_pickup_tasks(bid, schedule)
            if active_count > 0:
                return self._move_toward(bid, pos, self._nearest_drop(pos), blocked_dynamic)

        # P8: Has delivery task for active order
        task = schedule.peek_task(bid)
        if task and task.is_delivery():
            if task.order_idx == self._active_idx:
                if self._is_at_dropoff(pos) and len(inv) > 0:
                    schedule.pop_task(bid)
                    return {"bot": bid, "action": "drop_off"}
                if len(inv) > 0:
                    return self._move_toward(bid, pos, task.target_pos, blocked_dynamic)
            # Skip delivery tasks for non-active orders or empty inventory
            schedule.pop_task(bid)

        return self._fallback(bid, pos, active_count, blocked_dynamic)

    def _fallback(
        self,
        bid: int,
        pos: tuple[int, int],
        active_count: int,
        blocked: set[tuple[int, int]],
    ) -> dict[str, Any]:
        """Fallback when no scheduled task applies."""
        if active_count > 0:
            return self._move_toward(bid, pos, self._nearest_drop(pos), blocked)
        if self.gs.idle_spots:
            best = min(
                self.gs.idle_spots,
                key=lambda s: self.gs.dist_static(pos, s),
            )
            if pos != best:
                return self._move_toward(bid, pos, best, blocked)
        return {"bot": bid, "action": "wait"}

    def _skip_pickup_tasks(self, bid: int, schedule: Schedule) -> None:
        """Remove all leading pickup tasks from a bot's queue."""
        while True:
            task = schedule.peek_task(bid)
            if task and task.is_pickup():
                schedule.pop_task(bid)
            else:
                break

    # ------------------------------------------------------------------ #
    # Schedule management
    # ------------------------------------------------------------------ #

    def _get_or_build_schedule(self) -> Schedule:
        """Get cached schedule or build a new one."""
        cached: Schedule | None = self.gs._oracle_schedule
        needs_replan = cached is None or self._order_changed() or not self._schedule_valid(cached)
        if needs_replan:
            schedule = self._build_fresh_schedule()
            self.gs._oracle_schedule = schedule
            self.gs._oracle_last_order_idx = self._active_idx
            return schedule
        assert cached is not None
        return cached

    def _order_changed(self) -> bool:
        """Detect if the active order index changed since last schedule."""
        result: bool = self._active_idx != self.gs._oracle_last_order_idx
        return result

    def _schedule_valid(self, schedule: Schedule) -> bool:
        """Check if a cached schedule is still usable."""
        age = self.current_round - schedule.created_round
        if age > ORACLE_REPLAN_INTERVAL:
            return False
        return not schedule.is_empty

    def _build_fresh_schedule(self) -> Schedule:
        """Build a new schedule from current state."""
        scheduler = OracleScheduler(self.gs, self.items, self.drop_off, self.drop_off_zones)
        orders = self.gs.future_orders
        if not orders:
            return Schedule(created_round=self.current_round)
        return scheduler.build_schedule(
            orders,
            self._active_idx,
            self._bot_positions,
            self._bot_inventories,
            self.current_round,
        )

    def _detect_stuck_bots(self, schedule: Schedule) -> None:
        """Clear schedule for bots stuck in the same position too long."""
        stuck = self.gs._oracle_stuck_counts
        last = self.gs._oracle_last_pos
        for bid, pos in self._bot_positions.items():
            if last.get(bid) == pos:
                stuck[bid] = stuck.get(bid, 0) + 1
            else:
                stuck[bid] = 0
            last[bid] = pos
            if stuck.get(bid, 0) >= ORACLE_STUCK_THRESHOLD:
                schedule.clear_bot(bid)
                stuck[bid] = 0

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def _find_adjacent_needed(
        self,
        pos: tuple[int, int],
        active_needed: dict[str, int],
        inv: list[str],
        claimed_items: set[str],
    ) -> dict[str, Any] | None:
        """Find an adjacent item matching active needs minus what's carried."""
        remaining = dict(active_needed)
        for itype in inv:
            if remaining.get(itype, 0) > 0:
                remaining[itype] -= 1
        remaining = {k: v for k, v in remaining.items() if v > 0}
        if not remaining:
            return None
        for dx, dy in DIRECTIONS:
            for it in self._items_at_pos.get((pos[0] + dx, pos[1] + dy), []):
                if it["id"] not in claimed_items and remaining.get(it["type"], 0) > 0:
                    return it
        return None

    def _get_active_order(self) -> dict[str, Any] | None:
        for o in self.orders:
            if o.get("status") == "active" and not o["complete"]:
                return o
        return None

    def _get_active_needed(self, active: dict[str, Any]) -> dict[str, int]:
        needed: dict[str, int] = {}
        for item in active["items_required"]:
            needed[item] = needed.get(item, 0) + 1
        for item in active.get("items_delivered", []):
            needed[item] = needed.get(item, 0) - 1
        return {k: v for k, v in needed.items() if v > 0}

    def _count_active(self, inv: list[str], active_needed: dict[str, int]) -> int:
        remaining = dict(active_needed)
        count = 0
        for itype in inv:
            if remaining.get(itype, 0) > 0:
                count += 1
                remaining[itype] -= 1
        return count

    def _has_pending_picks(self, bid: int, schedule: Schedule) -> bool:
        return any(t.is_pickup() for t in schedule.tasks_for_bot(bid))

    def _is_at_dropoff(self, pos: tuple[int, int]) -> bool:
        return pos in self.drop_off_zones

    def _is_adjacent(self, pos: tuple[int, int], target: tuple[int, int]) -> bool:
        return abs(pos[0] - target[0]) + abs(pos[1] - target[1]) == 1

    def _nearest_drop(self, pos: tuple[int, int]) -> tuple[int, int]:
        if len(self.drop_off_zones) == 1:
            return self.drop_off_zones[0]
        best = self.drop_off_zones[0]
        best_d = self.gs.dist_static(pos, best)
        for zone in self.drop_off_zones[1:]:
            d = self.gs.dist_static(pos, zone)
            if d < best_d:
                best, best_d = zone, d
        return best

    def _move_toward(
        self,
        bid: int,
        pos: tuple[int, int],
        target: tuple[int, int],
        dynamic_blocked: set[tuple[int, int]],
    ) -> dict[str, Any]:
        """Move one step toward target, avoiding static + dynamic obstacles."""
        if pos == target:
            return {"bot": bid, "action": "wait"}
        blocked = self.gs.blocked_static | dynamic_blocked
        next_pos = bfs(pos, target, blocked)
        if next_pos is None:
            return {"bot": bid, "action": "wait"}
        direction = _delta_to_action(next_pos[0] - pos[0], next_pos[1] - pos[1])
        return {"bot": bid, "action": direction} if direction else {"bot": bid, "action": "wait"}

    def _action_destination(self, pos: tuple[int, int], action: dict[str, Any]) -> tuple[int, int]:
        act = action.get("action", "wait")
        deltas = {
            "move_up": (0, -1),
            "move_down": (0, 1),
            "move_left": (-1, 0),
            "move_right": (1, 0),
        }
        if act in deltas:
            dx, dy = deltas[act]
            return (pos[0] + dx, pos[1] + dy)
        return pos


def _pickup_action(bid: int, item_id: str) -> dict[str, Any]:
    """Build a pick_up action dict."""
    return {"bot": bid, "action": "pick_up", "item_id": item_id}


def _delta_to_action(dx: int, dy: int) -> str | None:
    """Convert a position delta to a move action string."""
    if dx == 1 and dy == 0:
        return "move_right"
    if dx == -1 and dy == 0:
        return "move_left"
    if dx == 0 and dy == 1:
        return "move_down"
    if dx == 0 and dy == -1:
        return "move_up"
    return None
