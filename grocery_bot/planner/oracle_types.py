"""Data structures for the Oracle Planner pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BotTask:
    """A single task assigned to a bot within the oracle schedule."""

    bot_id: int
    task_type: str  # "pick", "deliver", "move_to"
    target_pos: tuple[int, int]
    item_id: str | None = None
    item_type: str | None = None
    order_idx: int = 0

    def is_pickup(self) -> bool:
        """Return True if this is a pickup task."""
        return self.task_type == "pick"

    def is_delivery(self) -> bool:
        """Return True if this is a delivery task."""
        return self.task_type == "deliver"


@dataclass
class OrderPlan:
    """Plan for fulfilling a single order."""

    order_idx: int
    items_required: list[str]
    item_assignments: dict[str, int] = field(default_factory=dict)  # item_id -> bot_id
    estimated_rounds: int = 0

    @property
    def assigned_count(self) -> int:
        """Number of items that have been assigned to bots."""
        return len(self.item_assignments)

    @property
    def fully_assigned(self) -> bool:
        """True if all required items have been assigned."""
        return self.assigned_count >= len(self.items_required)


@dataclass
class Schedule:
    """Complete multi-order schedule for all bots."""

    order_plans: list[OrderPlan] = field(default_factory=list)
    bot_queues: dict[int, list[BotTask]] = field(default_factory=dict)
    horizon: int = 0
    created_round: int = 0

    @property
    def is_empty(self) -> bool:
        """True if no tasks are scheduled for any bot."""
        return not any(self.bot_queues.values())

    def tasks_for_bot(self, bot_id: int) -> list[BotTask]:
        """Return the task queue for a given bot."""
        return self.bot_queues.get(bot_id, [])

    def pop_task(self, bot_id: int) -> BotTask | None:
        """Remove and return the next task for a bot, or None."""
        queue = self.bot_queues.get(bot_id, [])
        if queue:
            return queue.pop(0)
        return None

    def peek_task(self, bot_id: int) -> BotTask | None:
        """Return the next task for a bot without removing it."""
        queue = self.bot_queues.get(bot_id, [])
        return queue[0] if queue else None

    def clear_bot(self, bot_id: int) -> None:
        """Remove all tasks for a bot."""
        self.bot_queues[bot_id] = []

    def pop_matching_pickup(self, bot_id: int, item_id: str) -> bool:
        """Remove a pickup task matching item_id from bot's queue."""
        queue = self.bot_queues.get(bot_id, [])
        for i, task in enumerate(queue):
            if task.is_pickup() and task.item_id == item_id:
                queue.pop(i)
                return True
        return False
