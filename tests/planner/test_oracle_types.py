"""Tests for oracle_types dataclasses."""

from grocery_bot.planner.oracle_types import BotTask, OrderPlan, Schedule


class TestBotTask:
    def test_is_pickup(self) -> None:
        task = BotTask(bot_id=0, task_type="pick", target_pos=(3, 4), item_id="i1")
        assert task.is_pickup()
        assert not task.is_delivery()

    def test_is_delivery(self) -> None:
        task = BotTask(bot_id=0, task_type="deliver", target_pos=(1, 8))
        assert task.is_delivery()
        assert not task.is_pickup()

    def test_move_to_neither(self) -> None:
        task = BotTask(bot_id=0, task_type="move_to", target_pos=(5, 5))
        assert not task.is_pickup()
        assert not task.is_delivery()

    def test_default_fields(self) -> None:
        task = BotTask(bot_id=1, task_type="pick", target_pos=(0, 0))
        assert task.item_id is None
        assert task.item_type is None
        assert task.order_idx == 0


class TestOrderPlan:
    def test_assigned_count_empty(self) -> None:
        plan = OrderPlan(order_idx=0, items_required=["apple", "banana"])
        assert plan.assigned_count == 0
        assert not plan.fully_assigned

    def test_fully_assigned(self) -> None:
        plan = OrderPlan(
            order_idx=0,
            items_required=["apple", "banana"],
            item_assignments={"i1": 0, "i2": 1},
        )
        assert plan.assigned_count == 2
        assert plan.fully_assigned

    def test_partially_assigned(self) -> None:
        plan = OrderPlan(
            order_idx=0,
            items_required=["a", "b", "c"],
            item_assignments={"i1": 0},
        )
        assert plan.assigned_count == 1
        assert not plan.fully_assigned


class TestSchedule:
    def test_is_empty_on_init(self) -> None:
        s = Schedule()
        assert s.is_empty

    def test_is_empty_with_empty_queues(self) -> None:
        s = Schedule(bot_queues={0: [], 1: []})
        assert s.is_empty

    def test_not_empty_with_tasks(self) -> None:
        task = BotTask(bot_id=0, task_type="pick", target_pos=(3, 4))
        s = Schedule(bot_queues={0: [task]})
        assert not s.is_empty

    def test_tasks_for_bot(self) -> None:
        t1 = BotTask(bot_id=0, task_type="pick", target_pos=(3, 4))
        t2 = BotTask(bot_id=0, task_type="deliver", target_pos=(1, 8))
        s = Schedule(bot_queues={0: [t1, t2]})
        assert s.tasks_for_bot(0) == [t1, t2]
        assert s.tasks_for_bot(99) == []

    def test_pop_task(self) -> None:
        t1 = BotTask(bot_id=0, task_type="pick", target_pos=(3, 4))
        t2 = BotTask(bot_id=0, task_type="deliver", target_pos=(1, 8))
        s = Schedule(bot_queues={0: [t1, t2]})
        popped = s.pop_task(0)
        assert popped == t1
        assert s.tasks_for_bot(0) == [t2]

    def test_pop_task_empty(self) -> None:
        s = Schedule(bot_queues={0: []})
        assert s.pop_task(0) is None
        assert s.pop_task(99) is None

    def test_peek_task(self) -> None:
        t1 = BotTask(bot_id=0, task_type="pick", target_pos=(3, 4))
        s = Schedule(bot_queues={0: [t1]})
        assert s.peek_task(0) == t1
        assert s.tasks_for_bot(0) == [t1]

    def test_peek_task_empty(self) -> None:
        s = Schedule()
        assert s.peek_task(0) is None

    def test_clear_bot(self) -> None:
        t1 = BotTask(bot_id=0, task_type="pick", target_pos=(3, 4))
        s = Schedule(bot_queues={0: [t1]})
        s.clear_bot(0)
        assert s.tasks_for_bot(0) == []
        assert s.is_empty

    def test_pop_matching_pickup_found(self) -> None:
        t1 = BotTask(bot_id=0, task_type="pick", target_pos=(3, 4), item_id="i1")
        t2 = BotTask(bot_id=0, task_type="pick", target_pos=(5, 6), item_id="i2")
        s = Schedule(bot_queues={0: [t1, t2]})
        assert s.pop_matching_pickup(0, "i2")
        assert len(s.tasks_for_bot(0)) == 1
        assert s.tasks_for_bot(0)[0].item_id == "i1"

    def test_pop_matching_pickup_not_found(self) -> None:
        t1 = BotTask(bot_id=0, task_type="deliver", target_pos=(1, 8))
        s = Schedule(bot_queues={0: [t1]})
        assert not s.pop_matching_pickup(0, "i99")
        assert len(s.tasks_for_bot(0)) == 1

    def test_pop_matching_pickup_empty_queue(self) -> None:
        s = Schedule(bot_queues={0: []})
        assert not s.pop_matching_pickup(0, "i1")
