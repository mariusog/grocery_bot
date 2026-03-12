"""Tests for OracleScheduler."""

import bot
from grocery_bot.planner.oracle_scheduler import OracleScheduler, _order_needs
from tests.conftest import make_state


def _make_scheduler(
    items: list | None = None,
    drop_off: tuple[int, int] = (1, 8),
    width: int = 11,
    height: int = 9,
) -> OracleScheduler:
    """Create an OracleScheduler with initialized GameState."""
    items = items or []
    state = make_state(
        items=items,
        drop_off=list(drop_off),
        width=width,
        height=height,
        bots=[{"id": 0, "position": [5, 4], "inventory": []}],
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
    bot.reset_state()
    bot.init_static(state)
    gs = bot._gs
    return OracleScheduler(gs, items, drop_off)


class TestOrderNeeds:
    def test_full_order(self) -> None:
        order = {
            "items_required": ["a", "a", "b"],
            "items_delivered": ["a"],
        }
        assert _order_needs(order) == {"a": 1, "b": 1}

    def test_future_stub(self) -> None:
        order = {"items_required": ["x", "x", "y"]}
        assert _order_needs(order) == {"x": 2, "y": 1}

    def test_empty_order(self) -> None:
        order = {"items_required": [], "items_delivered": []}
        assert _order_needs(order) == {}


class TestMatchItemsToNeeds:
    def test_matches_correct_types(self) -> None:
        items = [
            {"id": "i1", "type": "apple", "position": [3, 2]},
            {"id": "i2", "type": "banana", "position": [3, 4]},
            {"id": "i3", "type": "apple", "position": [5, 2]},
        ]
        scheduler = _make_scheduler(items)
        result = scheduler._match_items_to_needs({"apple": 1, "banana": 1})
        types = sorted(it["type"] for it in result)
        assert types == ["apple", "banana"]

    def test_respects_claimed(self) -> None:
        items = [
            {"id": "i1", "type": "apple", "position": [3, 2]},
            {"id": "i2", "type": "apple", "position": [5, 2]},
        ]
        scheduler = _make_scheduler(items)
        scheduler._claimed_items.add("i1")
        result = scheduler._match_items_to_needs({"apple": 1})
        assert len(result) == 1
        assert result[0]["id"] == "i2"

    def test_no_matching_items(self) -> None:
        items = [{"id": "i1", "type": "orange", "position": [3, 2]}]
        scheduler = _make_scheduler(items)
        assert scheduler._match_items_to_needs({"apple": 1}) == []


class TestCountCarriedActive:
    def test_counts_matching_inventory(self) -> None:
        items = [{"id": "i1", "type": "apple", "position": [3, 2]}]
        scheduler = _make_scheduler(items)
        orders = [{"items_required": ["apple", "banana"], "items_delivered": []}]
        inventories = {0: ["apple"], 1: ["banana", "cherry"]}
        result = scheduler._count_carried_active(inventories, orders, 0)
        assert result == {0: {"apple": 1}, 1: {"banana": 1}}

    def test_empty_inventories(self) -> None:
        scheduler = _make_scheduler()
        orders = [{"items_required": ["apple"]}]
        result = scheduler._count_carried_active({0: []}, orders, 0)
        assert result == {}


class TestBuildSchedule:
    def test_single_bot_single_order(self) -> None:
        items = [
            {"id": "i1", "type": "apple", "position": [3, 2]},
        ]
        scheduler = _make_scheduler(items)
        scheduler.gs.future_orders_recorded = 1
        orders = [{"items_required": ["apple"], "items_delivered": []}]
        schedule = scheduler.build_schedule(
            orders=orders,
            active_idx=0,
            bot_positions={0: (5, 4)},
            bot_inventories={0: []},
            current_round=0,
        )
        assert len(schedule.order_plans) == 1
        tasks = schedule.tasks_for_bot(0)
        assert len(tasks) >= 1
        assert any(t.is_pickup() for t in tasks)

    def test_empty_orders(self) -> None:
        scheduler = _make_scheduler()
        scheduler.gs.future_orders_recorded = 0
        schedule = scheduler.build_schedule(
            orders=[],
            active_idx=0,
            bot_positions={0: (5, 4)},
            bot_inventories={0: []},
            current_round=0,
        )
        assert schedule.is_empty

    def test_multi_order_creates_multiple_plans(self) -> None:
        items = [
            {"id": "i1", "type": "apple", "position": [3, 2]},
            {"id": "i2", "type": "banana", "position": [3, 4]},
        ]
        scheduler = _make_scheduler(items)
        scheduler.gs.future_orders_recorded = 2
        orders = [
            {"items_required": ["apple"]},
            {"items_required": ["banana"]},
        ]
        schedule = scheduler.build_schedule(
            orders=orders,
            active_idx=0,
            bot_positions={0: (5, 4)},
            bot_inventories={0: []},
            current_round=0,
        )
        assert len(schedule.order_plans) == 2

    def test_respects_inventory_limit(self) -> None:
        items = [{"id": f"i{n}", "type": "apple", "position": [3, 2]} for n in range(5)]
        scheduler = _make_scheduler(items)
        scheduler.gs.future_orders_recorded = 1
        orders = [{"items_required": ["apple"] * 5}]
        schedule = scheduler.build_schedule(
            orders=orders,
            active_idx=0,
            bot_positions={0: (5, 4)},
            bot_inventories={0: []},
            current_round=0,
        )
        tasks = schedule.tasks_for_bot(0)
        pick_tasks = [t for t in tasks if t.is_pickup()]
        deliver_tasks = [t for t in tasks if t.is_delivery()]
        # All 5 items assigned via multi-trip (3 + 2)
        assert len(pick_tasks) == 5
        # At least 2 delivery tasks (one per trip)
        assert len(deliver_tasks) >= 2
        # First delivery comes after at most 3 pickups
        first_deliver_idx = next(i for i, t in enumerate(tasks) if t.is_delivery())
        picks_before = sum(1 for t in tasks[:first_deliver_idx] if t.is_pickup())
        assert picks_before <= 3

    def test_carried_items_reduce_needs(self) -> None:
        items = [
            {"id": "i1", "type": "apple", "position": [3, 2]},
            {"id": "i2", "type": "banana", "position": [3, 4]},
        ]
        scheduler = _make_scheduler(items)
        scheduler.gs.future_orders_recorded = 1
        orders = [
            {"items_required": ["apple", "banana"], "items_delivered": []},
        ]
        # Bot already carrying apple
        schedule = scheduler.build_schedule(
            orders=orders,
            active_idx=0,
            bot_positions={0: (5, 4)},
            bot_inventories={0: ["apple"]},
            current_round=0,
        )
        pick_tasks = [t for t in schedule.tasks_for_bot(0) if t.is_pickup()]
        # Should only need to pick banana
        picked_types = [t.item_type for t in pick_tasks]
        assert "apple" not in picked_types
