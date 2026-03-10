"""Delivery queue, role assignment, and persistent task management."""

import math

from grocery_bot.constants import (
    MAX_INVENTORY,
    TASK_COMMITMENT_ROUNDS,
)
from grocery_bot.planner._base import PlannerBase


def role_to_task_type(role: str) -> str:
    """Map a role name to its corresponding task type."""
    return {"pick": "pick", "deliver": "deliver", "preview": "preview"}.get(role, "idle")


class CoordinationMixin(PlannerBase):
    """Mixin providing delivery queue, role assignment, and task management."""

    def _check_order_transition(self) -> None:
        """Detect when the active order changes and clear persistent state."""
        current_id = self.active["id"] if self.active else None
        if self.gs.last_active_order_id is not None and current_id != self.gs.last_active_order_id:
            self.gs.delivery_queue.clear()
            self.gs.bot_tasks.clear()
        self.gs.last_active_order_id = current_id

    def _update_delivery_queue(self) -> None:
        """Maintain the delivery queue for dropoff congestion control."""
        gs = self.gs

        alive_ids = {b["id"] for b in self.bots}
        gs.delivery_queue = [
            bid
            for bid in gs.delivery_queue
            if bid in alive_ids and self.bot_has_active.get(bid, False)
        ]

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
            should_queue = False

            assigned_empty = bid in self.bot_assignments and not self.bot_assignments[bid]
            unassigned_idle = bid not in self.bot_assignments and self.active_on_shelves == 0
            full_inv = len(inv) >= MAX_INVENTORY
            if full_inv or self.active_on_shelves == 0 or assigned_empty or unassigned_idle:
                should_queue = True

            if should_queue:
                d_to_drop = self.gs.dist_static(pos, self._nearest_dropoff(pos))
                n_active = sum(self.bot_carried_active.get(bid, {}).values())
                new_candidates.append((d_to_drop, -n_active, bid))

        new_candidates.sort()
        for _, _, bid in new_candidates:
            gs.delivery_queue.append(bid)

    def _assign_roles(self) -> None:
        """Assign roles to bots: 'pick', 'deliver', 'preview', 'idle'."""
        gs = self.gs
        num_bots = len(self.bots)

        if self.cfg.use_predictions:
            active_picker_count = min(self.active_on_shelves, num_bots - 1)
        else:
            active_picker_count = math.ceil(self.active_on_shelves / MAX_INVENTORY)
            active_picker_count = (
                min(active_picker_count, num_bots - 1) if num_bots > 1 else num_bots
            )

        # W5: when the full wave is ready, admit all bots to deliver simultaneously.
        if self.wave_mode and self.wave_on_shelves == 0:
            max_deliverers = len(self.bots)
        else:
            max_deliverers = self.cfg.max_concurrent_deliverers

        for delivering_count, bid in enumerate(gs.delivery_queue):
            if delivering_count >= max_deliverers:
                break
            self.bot_roles[bid] = "deliver"

        picker_candidates: list[tuple[float, int]] = []
        for bot in self.bots:
            bid = bot["id"]
            if bid in self.bot_roles:
                continue
            if self.bot_has_active.get(bid, False):
                self.bot_roles[bid] = "pick"
                continue
            if self.bot_assignments.get(bid):
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

        if self.preview and self.net_preview:
            for bid in self.preview_bot_ids:
                if bid not in self.bot_roles:
                    self.bot_roles[bid] = "preview"
            if self.cfg.extra_preview_roles:
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

        for bot in self.bots:
            bid = bot["id"]
            if bid not in self.bot_roles:
                self.bot_roles[bid] = "idle"

    def _update_persistent_tasks(self) -> None:
        """Update persistent task assignments, respecting commitment periods."""
        gs = self.gs

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

            if task["type"] == "pick":
                target_type = task.get("item_type")
                if target_type and self.net_active.get(target_type, 0) <= 0:
                    del gs.bot_tasks[bid]
                    continue
                item_id = task.get("item_id")
                if item_id and item_id in gs.blacklisted_items:
                    del gs.bot_tasks[bid]
                    continue
            elif task["type"] == "deliver":
                if not self.bot_has_active.get(bid, False):
                    del gs.bot_tasks[bid]
                    continue

        for bot in self.bots:
            bid = bot["id"]
            role = self.bot_roles.get(bid, "idle")

            if bid in gs.bot_tasks:
                task = gs.bot_tasks[bid]
                if task.get("committed_until", 0) > self.current_round and task[
                    "type"
                ] == role_to_task_type(role):
                    continue

            if role == "deliver":
                pos = tuple(self.bots_by_id[bid]["position"])
                gs.bot_tasks[bid] = {
                    "type": "deliver",
                    "target": self._nearest_dropoff(pos),
                    "committed_until": self.current_round + TASK_COMMITMENT_ROUNDS,
                }
            elif role == "pick":
                if self.bot_assignments.get(bid):
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
