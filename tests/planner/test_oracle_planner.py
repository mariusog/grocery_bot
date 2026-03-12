"""Tests for OraclePlanner — per-round action execution."""

import bot
from grocery_bot.planner.oracle_planner import OraclePlanner, _delta_to_action
from grocery_bot.planner.oracle_types import BotTask, Schedule
from tests.conftest import get_action, make_state


def _setup_gs(state: dict) -> None:
    """Initialize GameState from a state dict."""
    bot.reset_state()
    bot._gs.init_static(state)


def _make_oracle_planner(
    bots: list | None = None,
    items: list | None = None,
    orders: list | None = None,
    drop_off: list | None = None,
    width: int = 11,
    height: int = 9,
    round_num: int = 10,
    future_orders: list | None = None,
    future_recorded: int = 10,
) -> OraclePlanner:
    """Create an OraclePlanner with initialized state."""
    state = make_state(
        bots=bots or [{"id": 0, "position": [5, 4], "inventory": []}],
        items=items or [],
        orders=orders
        or [
            {
                "id": "o0",
                "items_required": ["apple"],
                "items_delivered": [],
                "complete": False,
                "status": "active",
            }
        ],
        drop_off=drop_off or [1, 8],
        width=width,
        height=height,
        round_num=round_num,
    )
    _setup_gs(state)
    gs = bot._gs
    if future_orders:
        gs.set_future_orders(future_orders, recorded_count=future_recorded)
    return OraclePlanner(gs, state, full_state=state)


class TestDeltaToAction:
    def test_right(self) -> None:
        assert _delta_to_action(1, 0) == "move_right"

    def test_left(self) -> None:
        assert _delta_to_action(-1, 0) == "move_left"

    def test_down(self) -> None:
        assert _delta_to_action(0, 1) == "move_down"

    def test_up(self) -> None:
        assert _delta_to_action(0, -1) == "move_up"

    def test_invalid(self) -> None:
        assert _delta_to_action(1, 1) is None
        assert _delta_to_action(0, 0) is None


class TestOraclePlannerBasics:
    def test_no_active_order_waits(self) -> None:
        planner = _make_oracle_planner(
            orders=[
                {
                    "id": "o0",
                    "items_required": [],
                    "items_delivered": [],
                    "complete": True,
                    "status": "active",
                }
            ],
        )
        actions = planner.plan()
        assert len(actions) == 1
        assert actions[0]["action"] == "wait"

    def test_at_dropoff_with_active_items_drops(self) -> None:
        planner = _make_oracle_planner(
            bots=[{"id": 0, "position": [1, 8], "inventory": ["apple"]}],
            orders=[
                {
                    "id": "o0",
                    "items_required": ["apple"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                }
            ],
        )
        actions = planner.plan()
        assert get_action(actions, 0)["action"] == "drop_off"

    def test_returns_action_per_bot(self) -> None:
        planner = _make_oracle_planner(
            bots=[
                {"id": 0, "position": [3, 4], "inventory": []},
                {"id": 1, "position": [5, 4], "inventory": []},
            ],
        )
        actions = planner.plan()
        assert len(actions) == 2
        bot_ids = {a["bot"] for a in actions}
        assert bot_ids == {0, 1}


class TestOraclePlannerScheduleExecution:
    def test_pickup_adjacent_item(self) -> None:
        """Bot adjacent to assigned pickup item should pick it up."""
        items = [{"id": "i1", "type": "apple", "position": [4, 4]}]
        planner = _make_oracle_planner(
            bots=[{"id": 0, "position": [5, 4], "inventory": []}],
            items=items,
            future_orders=[{"items_required": ["apple"]}],
        )
        task = BotTask(
            bot_id=0,
            task_type="pick",
            target_pos=(5, 4),
            item_id="i1",
            item_type="apple",
            order_idx=0,
        )
        schedule = Schedule(bot_queues={0: [task]}, created_round=10)
        planner.gs._oracle_schedule = schedule
        planner.gs._oracle_last_order_idx = 0
        actions = planner.plan()
        action = get_action(actions, 0)
        assert action["action"] == "pick_up"
        assert action["item_id"] == "i1"

    def test_move_toward_pickup(self) -> None:
        """Bot with distant pickup task should move toward it."""
        items = [{"id": "i1", "type": "apple", "position": [3, 2]}]
        planner = _make_oracle_planner(
            bots=[{"id": 0, "position": [5, 4], "inventory": []}],
            items=items,
            future_orders=[{"items_required": ["apple"]}],
        )
        task = BotTask(
            bot_id=0,
            task_type="pick",
            target_pos=(2, 2),
            item_id="i1",
            item_type="apple",
            order_idx=0,
        )
        schedule = Schedule(bot_queues={0: [task]}, created_round=10)
        planner.gs._oracle_schedule = schedule
        planner.gs._oracle_last_order_idx = 0
        actions = planner.plan()
        action = get_action(actions, 0)
        assert action["action"].startswith("move_")

    def test_delivery_task_at_dropoff(self) -> None:
        """Bot at dropoff with delivery task and items should drop off."""
        planner = _make_oracle_planner(
            bots=[{"id": 0, "position": [1, 8], "inventory": ["apple"]}],
            orders=[
                {
                    "id": "o0",
                    "items_required": ["apple"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                }
            ],
        )
        task = BotTask(bot_id=0, task_type="deliver", target_pos=(1, 8), order_idx=0)
        schedule = Schedule(bot_queues={0: [task]}, created_round=10)
        planner.gs._oracle_schedule = schedule
        planner.gs._oracle_last_order_idx = 0
        actions = planner.plan()
        assert get_action(actions, 0)["action"] == "drop_off"

    def test_opportunistic_adjacent_pickup(self) -> None:
        """Bot adjacent to needed item picks it up even without schedule."""
        items = [{"id": "i1", "type": "apple", "position": [4, 4]}]
        planner = _make_oracle_planner(
            bots=[{"id": 0, "position": [5, 4], "inventory": []}],
            items=items,
            orders=[
                {
                    "id": "o0",
                    "items_required": ["apple"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                }
            ],
        )
        # Empty schedule
        schedule = Schedule(bot_queues={0: []}, created_round=10)
        planner.gs._oracle_schedule = schedule
        planner.gs._oracle_last_order_idx = 0
        actions = planner.plan()
        action = get_action(actions, 0)
        assert action["action"] == "pick_up"
        assert action["item_id"] == "i1"

    def test_skip_missing_item_task(self) -> None:
        """Bot skips pickup task when item no longer exists on map."""
        planner = _make_oracle_planner(
            bots=[{"id": 0, "position": [5, 4], "inventory": []}],
            items=[],  # no items on map
        )
        task = BotTask(
            bot_id=0,
            task_type="pick",
            target_pos=(3, 2),
            item_id="i_gone",
            item_type="apple",
            order_idx=0,
        )
        schedule = Schedule(bot_queues={0: [task]}, created_round=10)
        planner.gs._oracle_schedule = schedule
        planner.gs._oracle_last_order_idx = 0
        actions = planner.plan()
        # Should not crash, should wait or idle
        assert get_action(actions, 0)["action"] in (
            "wait",
            "move_up",
            "move_down",
            "move_left",
            "move_right",
        )


class TestOraclePlannerHelpers:
    def test_count_active(self) -> None:
        planner = _make_oracle_planner()
        assert planner._count_active(["apple", "banana"], {"apple": 1, "banana": 1}) == 2
        assert planner._count_active(["apple", "apple"], {"apple": 1}) == 1
        assert planner._count_active(["cherry"], {"apple": 1}) == 0

    def test_is_adjacent(self) -> None:
        planner = _make_oracle_planner()
        assert planner._is_adjacent((5, 4), (4, 4))
        assert planner._is_adjacent((5, 4), (5, 5))
        assert not planner._is_adjacent((5, 4), (3, 4))
        assert not planner._is_adjacent((5, 4), (5, 4))

    def test_is_at_dropoff(self) -> None:
        planner = _make_oracle_planner(drop_off=[1, 8])
        assert planner._is_at_dropoff((1, 8))
        assert not planner._is_at_dropoff((5, 4))

    def test_action_destination(self) -> None:
        planner = _make_oracle_planner()
        pos = (5, 4)
        assert planner._action_destination(pos, {"action": "move_up"}) == (5, 3)
        assert planner._action_destination(pos, {"action": "move_down"}) == (5, 5)
        assert planner._action_destination(pos, {"action": "wait"}) == (5, 4)


class TestScheduleValidity:
    def test_old_schedule_invalid(self) -> None:
        planner = _make_oracle_planner(round_num=50)
        schedule = Schedule(
            bot_queues={0: [BotTask(0, "pick", (3, 4))]},
            created_round=10,
        )
        assert not planner._schedule_valid(schedule)

    def test_recent_schedule_valid(self) -> None:
        planner = _make_oracle_planner(round_num=15)
        schedule = Schedule(
            bot_queues={0: [BotTask(0, "pick", (3, 4))]},
            created_round=10,
        )
        assert planner._schedule_valid(schedule)

    def test_empty_schedule_invalid(self) -> None:
        planner = _make_oracle_planner(round_num=10)
        schedule = Schedule(bot_queues={}, created_round=10)
        assert not planner._schedule_valid(schedule)

    def test_order_change_triggers_replan(self) -> None:
        planner = _make_oracle_planner(round_num=10)
        planner.gs._oracle_last_order_idx = 0
        planner._active_idx = 1
        assert planner._order_changed()

    def test_same_order_no_replan(self) -> None:
        planner = _make_oracle_planner(round_num=10)
        planner.gs._oracle_last_order_idx = 0
        planner._active_idx = 0
        assert not planner._order_changed()


class TestStuckDetection:
    def test_stuck_bot_cleared(self) -> None:
        planner = _make_oracle_planner(
            bots=[{"id": 0, "position": [5, 4], "inventory": []}],
        )
        task = BotTask(0, "pick", (3, 2), item_id="i1")
        schedule = Schedule(bot_queues={0: [task]}, created_round=10)
        # Simulate being stuck for ORACLE_STUCK_THRESHOLD rounds
        planner.gs._oracle_stuck_counts = {0: 4}
        planner.gs._oracle_last_pos = {0: (5, 4)}
        planner._detect_stuck_bots(schedule)
        # Bot was stuck 5 rounds, schedule should be cleared
        assert schedule.tasks_for_bot(0) == []

    def test_moving_bot_not_cleared(self) -> None:
        planner = _make_oracle_planner(
            bots=[{"id": 0, "position": [5, 4], "inventory": []}],
        )
        task = BotTask(0, "pick", (3, 2), item_id="i1")
        schedule = Schedule(bot_queues={0: [task]}, created_round=10)
        # Bot was at different position last round
        planner.gs._oracle_stuck_counts = {0: 0}
        planner.gs._oracle_last_pos = {0: (4, 4)}
        planner._detect_stuck_bots(schedule)
        assert len(schedule.tasks_for_bot(0)) == 1
