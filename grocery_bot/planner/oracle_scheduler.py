"""OracleScheduler — builds a global multi-order execution plan."""

from __future__ import annotations

from typing import Any

from grocery_bot.constants import MAX_INVENTORY, ORACLE_PLANNING_HORIZON
from grocery_bot.orders import get_needed_items
from grocery_bot.planner.oracle_types import BotTask, OrderPlan, Schedule


class OracleScheduler:
    """Builds a global schedule from oracle order knowledge."""

    def __init__(
        self,
        gs: Any,
        items: list[dict[str, Any]],
        drop_off: tuple[int, int],
        drop_off_zones: list[tuple[int, int]] | None = None,
    ) -> None:
        self.gs = gs
        self.items = items
        self.drop_off = drop_off
        self.drop_off_zones = drop_off_zones or [drop_off]
        self._items_by_type: dict[str, list[dict[str, Any]]] = {}
        for it in items:
            self._items_by_type.setdefault(it["type"], []).append(it)
        self._claimed_items: set[str] = set()

    def build_schedule(
        self,
        orders: list[dict[str, Any]],
        active_idx: int,
        bot_positions: dict[int, tuple[int, int]],
        bot_inventories: dict[int, list[str]],
        current_round: int,
    ) -> Schedule:
        """Build a complete schedule spanning multiple orders."""
        self._claimed_items = set()
        schedule = Schedule(created_round=current_round)
        projected = dict(bot_positions)
        inv_counts = {bid: len(inv) for bid, inv in bot_inventories.items()}

        carried_active = self._count_carried_active(bot_inventories, orders, active_idx)

        horizon_end = min(len(orders), active_idx + ORACLE_PLANNING_HORIZON)
        if self.gs.future_orders_recorded > 0:
            horizon_end = min(horizon_end, self.gs.future_orders_recorded)

        schedule.horizon = horizon_end - active_idx
        for bot_id in bot_positions:
            schedule.bot_queues[bot_id] = []

        for oidx in range(active_idx, horizon_end):
            order = orders[oidx]
            carried = carried_active if oidx == active_idx else {}
            order_plan = self._plan_single_order(
                order,
                oidx,
                projected,
                inv_counts,
                carried,
                schedule,
            )
            schedule.order_plans.append(order_plan)
            self._update_projections(schedule, projected, inv_counts)

        return schedule

    def _plan_single_order(
        self,
        order: dict[str, Any],
        order_idx: int,
        projected: dict[int, tuple[int, int]],
        inv_counts: dict[int, int],
        carried: dict[int, dict[str, int]],
        schedule: Schedule,
    ) -> OrderPlan:
        """Plan pickup and delivery for a single order (multi-trip)."""
        items_req = order.get("items_required", [])
        needed = _order_needs(order)

        for _bid, carried_types in carried.items():
            for itype, cnt in carried_types.items():
                if itype in needed:
                    needed[itype] = max(0, needed[itype] - cnt)
        needed = {k: v for k, v in needed.items() if v > 0}

        plan = OrderPlan(order_idx=order_idx, items_required=list(items_req))
        all_items = self._match_items_to_needs(needed, projected)
        if not all_items and not carried:
            return plan

        # Handle bots already carrying active items first
        bots_with_items: set[int] = set()
        for bid in carried:
            if sum(carried[bid].values()) > 0:
                bots_with_items.add(bid)

        # Multi-trip loop: assign items in batches until all assigned
        remaining_items = list(all_items)
        trip = 0
        while remaining_items and trip < 3:
            assignments = self._assign_items(
                remaining_items,
                projected,
                inv_counts,
                schedule,
            )
            if not assignments:
                break

            assigned_ids: set[str] = set()
            for bot_id, bot_items in assignments.items():
                bot_pos = projected.get(bot_id, (0, 0))
                drop = self._nearest_drop(bot_pos)
                pickup_tasks = self._build_pickup_tasks(
                    bot_id,
                    bot_pos,
                    bot_items,
                    order_idx,
                    drop,
                )
                for task in pickup_tasks:
                    schedule.bot_queues.setdefault(bot_id, []).append(task)
                    plan.item_assignments[task.item_id or ""] = bot_id
                    self._claimed_items.add(task.item_id or "")
                    assigned_ids.add(task.item_id or "")
                bots_with_items.add(bot_id)

            # Add delivery tasks for this batch
            for bot_id in bots_with_items:
                drop = self._nearest_drop(projected.get(bot_id, (0, 0)))
                deliver_task = BotTask(
                    bot_id=bot_id,
                    task_type="deliver",
                    target_pos=drop,
                    order_idx=order_idx,
                )
                schedule.bot_queues.setdefault(bot_id, []).append(deliver_task)

            # Update projections for next trip
            self._update_projections(schedule, projected, inv_counts)
            remaining_items = [it for it in remaining_items if it["id"] not in assigned_ids]
            bots_with_items = set()
            trip += 1

        # If first trip had carried items but no picks, still deliver
        if trip == 0 and carried:
            for bid in carried:
                if sum(carried[bid].values()) > 0:
                    drop = self._nearest_drop(projected.get(bid, (0, 0)))
                    deliver_task = BotTask(
                        bot_id=bid,
                        task_type="deliver",
                        target_pos=drop,
                        order_idx=order_idx,
                    )
                    schedule.bot_queues.setdefault(bid, []).append(deliver_task)

        plan.estimated_rounds = self._estimate_order_rounds(plan, projected)
        return plan

    def _match_items_to_needs(
        self,
        needed: dict[str, int],
        bot_positions: dict[int, tuple[int, int]] | None = None,
    ) -> list[dict[str, Any]]:
        """Find physical map items matching needed types, preferring closer ones."""
        result: list[dict[str, Any]] = []
        for item_type, count in needed.items():
            available = [
                it
                for it in self._items_by_type.get(item_type, [])
                if it["id"] not in self._claimed_items
            ]
            if bot_positions and len(available) > count:
                # Sort by pickup distance to nearest bot
                available.sort(
                    key=lambda it: min(
                        self.gs.find_best_item_target(bp, it)[1] for bp in bot_positions.values()
                    )
                )
            for it in available[:count]:
                result.append(it)
        return result

    def _assign_items(
        self,
        items: list[dict[str, Any]],
        projected: dict[int, tuple[int, int]],
        inv_counts: dict[int, int],
        schedule: Schedule,
    ) -> dict[int, list[dict[str, Any]]]:
        """Assign items to bots, respecting inventory limits."""
        assignable: list[tuple[int, tuple[int, int], int]] = []
        for bid, pos in projected.items():
            pending = self._pending_picks_after_last_deliver(bid, schedule)
            current_inv = inv_counts.get(bid, 0)
            spare = MAX_INVENTORY - current_inv - pending
            if spare > 0:
                assignable.append((bid, pos, spare))

        if not assignable or not items:
            return {}

        # Use Hungarian for balanced distribution, then fill remaining greedily
        result: dict[int, list[dict[str, Any]]] = self.gs.assign_items_to_bots(
            assignable, items, drop_off=self.drop_off
        )
        # Hungarian gives 1-to-1. Fill remaining items to bots with spare slots.
        assigned_ids = {it["id"] for its in result.values() for it in its}
        remaining = [it for it in items if it["id"] not in assigned_ids]
        if remaining:
            bot_counts = {bid: len(its) for bid, its in result.items()}
            spare_bots = [
                (bid, pos, slots - bot_counts.get(bid, 0))
                for bid, pos, slots in assignable
                if slots - bot_counts.get(bid, 0) > 0
            ]
            if spare_bots:
                extra = self._greedy_multi_assign(spare_bots, remaining)
                for bid, its in extra.items():
                    result.setdefault(bid, []).extend(its)
        return result

    def _greedy_multi_assign(
        self,
        assignable: list[tuple[int, tuple[int, int], int]],
        items: list[dict[str, Any]],
    ) -> dict[int, list[dict[str, Any]]]:
        """Greedily assign items to bots, allowing multiple items per bot."""
        result: dict[int, list[dict[str, Any]]] = {}
        remaining_slots = {bid: slots for bid, _, slots in assignable}
        assigned_items: set[int] = set()
        # Build cost pairs: (cost, bot_idx, item_idx)
        pairs: list[tuple[float, int, int]] = []
        for bi, (_, bot_pos, _) in enumerate(assignable):
            for ii, it in enumerate(items):
                _, d = self.gs.find_best_item_target(bot_pos, it)
                pairs.append((d, bi, ii))
        pairs.sort()
        for _cost, bi, ii in pairs:
            if ii in assigned_items:
                continue
            bot_id = assignable[bi][0]
            if remaining_slots[bot_id] <= 0:
                continue
            result.setdefault(bot_id, []).append(items[ii])
            remaining_slots[bot_id] -= 1
            assigned_items.add(ii)
            if len(assigned_items) >= len(items):
                break
        return result

    @staticmethod
    def _pending_picks_after_last_deliver(
        bid: int,
        schedule: Schedule,
    ) -> int:
        """Count pickup tasks after the last delivery in a bot's queue."""
        tasks = schedule.tasks_for_bot(bid)
        count = 0
        for task in reversed(tasks):
            if task.is_delivery():
                break
            if task.is_pickup():
                count += 1
        return count

    def _build_pickup_tasks(
        self,
        bot_id: int,
        bot_pos: tuple[int, int],
        items: list[dict[str, Any]],
        order_idx: int,
        drop_off: tuple[int, int],
    ) -> list[BotTask]:
        """Build TSP-ordered pickup tasks for a bot's assigned items."""
        targets = []
        for item in items:
            pickup_pos = self._best_pickup_pos(bot_pos, item)
            targets.append((item, pickup_pos))
        if len(targets) > 1:
            tsp_input = [(it["id"], pos) for it, pos in targets]
            ordered = self.gs.tsp_route(bot_pos, tsp_input, drop_off)
            id_order = [iid for iid, _ in ordered]
            target_map = {it["id"]: (it, pos) for it, pos in targets}
            targets = [target_map[iid] for iid in id_order]
        return [
            BotTask(
                bot_id=bot_id,
                task_type="pick",
                target_pos=pos,
                item_id=it["id"],
                item_type=it["type"],
                order_idx=order_idx,
            )
            for it, pos in targets
        ]

    def _best_pickup_pos(self, bot_pos: tuple[int, int], item: dict[str, Any]) -> tuple[int, int]:
        """Find the best adjacent position to pick up an item."""
        result = self.gs.find_best_item_target(bot_pos, item)
        cell: tuple[int, int] | None = result[0]
        if cell is None:
            return bot_pos
        return cell

    def _nearest_drop(self, pos: tuple[int, int]) -> tuple[int, int]:
        """Return the nearest drop-off zone."""
        if len(self.drop_off_zones) == 1:
            return self.drop_off_zones[0]
        best = self.drop_off_zones[0]
        best_d = self.gs.dist_static(pos, best)
        for zone in self.drop_off_zones[1:]:
            d = self.gs.dist_static(pos, zone)
            if d < best_d:
                best, best_d = zone, d
        return best

    def _count_carried_active(
        self,
        bot_inventories: dict[int, list[str]],
        orders: list[dict[str, Any]],
        active_idx: int,
    ) -> dict[int, dict[str, int]]:
        """Count items each bot carries that match the active order."""
        if active_idx >= len(orders):
            return {}
        needed = _order_needs(orders[active_idx])
        result: dict[int, dict[str, int]] = {}
        remaining = dict(needed)
        for bid, inv in bot_inventories.items():
            carried: dict[str, int] = {}
            for itype in inv:
                if remaining.get(itype, 0) > 0:
                    carried[itype] = carried.get(itype, 0) + 1
                    remaining[itype] -= 1
            if carried:
                result[bid] = carried
        return result

    def _update_projections(
        self,
        schedule: Schedule,
        projected: dict[int, tuple[int, int]],
        inv_counts: dict[int, int],
    ) -> None:
        """Update projected positions based on the last tasks in schedule."""
        for bid, tasks in schedule.bot_queues.items():
            if tasks:
                last = tasks[-1]
                projected[bid] = last.target_pos
                picks = sum(1 for t in tasks if t.is_pickup())
                delivers = sum(1 for t in tasks if t.is_delivery())
                inv_counts[bid] = 0 if delivers > 0 else min(MAX_INVENTORY, picks)

    def _estimate_order_rounds(
        self,
        plan: OrderPlan,
        projected: dict[int, tuple[int, int]],
    ) -> int:
        """Rough estimate of rounds to complete an order."""
        if not plan.item_assignments:
            return 0
        max_dist = 0
        for _item_id, bot_id in plan.item_assignments.items():
            pos = projected.get(bot_id, (0, 0))
            d = self.gs.dist_static(pos, self.drop_off)
            if d > max_dist and d < float("inf"):
                max_dist = int(d)
        return max_dist + len(plan.items_required) * 2


def _order_needs(order: dict[str, Any]) -> dict[str, int]:
    """Get needed items, handling both full orders and future order stubs."""
    if "items_delivered" in order:
        return get_needed_items(order)
    needed: dict[str, int] = {}
    for item_type in order.get("items_required", []):
        needed[item_type] = needed.get(item_type, 0) + 1
    return needed
