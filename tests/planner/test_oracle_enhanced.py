"""Tests for OracleEnhancedPlanner — oracle knowledge enhancements."""

import bot
from grocery_bot.planner.oracle_enhanced import OracleEnhancedPlanner
from tests.conftest import make_state
from tests.planner.conftest import _active_order, _preview_order


def _make_oracle_planner(
    bots=None,
    items=None,
    orders=None,
    drop_off=None,
    width=11,
    height=9,
    round_num=0,
    max_rounds=300,
    future_orders=None,
):
    """Create an OracleEnhancedPlanner with oracle knowledge."""
    state = make_state(
        bots=bots or [],
        items=items or [],
        orders=orders or [],
        drop_off=drop_off or [1, 8],
        width=width,
        height=height,
        round_num=round_num,
        max_rounds=max_rounds,
    )
    bot.reset_state()
    bot.decide_actions(state)
    gs = bot._gs
    if future_orders:
        gs.set_future_orders(future_orders, recorded_count=len(future_orders))
        gs.update_demand(0)
    planner = OracleEnhancedPlanner(gs, state, full_state=state)
    planner.plan()
    return planner


def test_oracle_enhanced_identical_without_knowledge():
    """OracleEnhancedPlanner produces same actions as RoundPlanner with no oracle."""
    items = [
        {"id": "i1", "type": "milk", "position": [3, 2]},
        {"id": "i2", "type": "bread", "position": [3, 4]},
    ]
    bots = [{"id": 0, "position": [2, 2], "inventory": []}]
    orders = [_active_order(["milk"])]

    state = make_state(bots=bots, items=items, orders=orders)
    bot.reset_state()
    reactive_actions = bot.decide_actions(state)

    bot.reset_state()
    bot.decide_actions(state)
    gs = bot._gs
    oracle_planner = OracleEnhancedPlanner(gs, state, full_state=state)
    oracle_actions = oracle_planner.plan()

    assert len(oracle_actions) == len(reactive_actions)
    for oa, ra in zip(oracle_actions, reactive_actions, strict=True):
        assert oa["action"] == ra["action"]


def test_deep_oracle_needs_extends_lookahead():
    """Oracle enhanced planner looks further ahead than base."""
    future = [
        {"id": "o0", "items_required": ["milk"]},
        {"id": "o1", "items_required": ["bread"]},
        {"id": "o2", "items_required": ["cheese"]},
        {"id": "o3", "items_required": ["yogurt"]},
        {"id": "o4", "items_required": ["butter"]},
        {"id": "o5", "items_required": ["eggs"]},
        {"id": "o6", "items_required": ["ham"]},
        {"id": "o7", "items_required": ["juice"]},
    ]
    items = [
        {"id": f"i{i}", "type": t, "position": [3, i]}
        for i, t in enumerate(["milk", "bread", "cheese", "yogurt", "butter", "eggs"], start=1)
    ]
    bots = [{"id": 0, "position": [2, 1], "inventory": []}]
    orders = [_active_order(["milk"]), _preview_order(["bread"])]

    p = _make_oracle_planner(bots=bots, items=items, orders=orders, future_orders=future)
    # Deep lookahead: should see orders N+2 through N+7 (up to 6 ahead)
    # cheese, yogurt, butter, eggs should all appear in oracle_needs
    assert "cheese" in p.oracle_needs
    assert "yogurt" in p.oracle_needs
    assert "butter" in p.oracle_needs
    assert "eggs" in p.oracle_needs


def test_oracle_item_value_computed():
    """oracle_item_value is populated when oracle knowledge available."""
    future = [
        {"id": "o0", "items_required": ["milk"]},
        {"id": "o1", "items_required": ["bread"]},
        {"id": "o2", "items_required": ["milk", "cheese"]},
        {"id": "o3", "items_required": ["milk", "bread"]},
    ]
    items = [
        {"id": "i1", "type": "milk", "position": [3, 2]},
        {"id": "i2", "type": "bread", "position": [3, 4]},
        {"id": "i3", "type": "cheese", "position": [3, 6]},
    ]
    bots = [{"id": 0, "position": [2, 2], "inventory": []}]
    orders = [_active_order(["milk"]), _preview_order(["bread"])]

    p = _make_oracle_planner(bots=bots, items=items, orders=orders, future_orders=future)
    # milk appears in orders o2 and o3 -> value 2.0
    assert p.oracle_item_value.get("milk", 0) == 2.0
    # cheese appears in o2 -> value 1.0
    assert p.oracle_item_value.get("cheese", 0) == 1.0
    # bread appears in o3 -> value 1.0
    assert p.oracle_item_value.get("bread", 0) == 1.0


def test_oracle_item_value_empty_without_knowledge():
    """oracle_item_value is empty when no oracle knowledge."""
    items = [{"id": "i1", "type": "milk", "position": [3, 2]}]
    bots = [{"id": 0, "position": [2, 2], "inventory": []}]
    orders = [_active_order(["milk"])]

    p = _make_oracle_planner(bots=bots, items=items, orders=orders)
    assert p.oracle_item_value == {}


def test_spec_target_prefers_oracle_high_demand():
    """Speculative target selection prefers items with higher oracle demand."""
    future = [
        {"id": "o0", "items_required": ["cheese"]},
        {"id": "o1", "items_required": ["yogurt"]},
        {"id": "o2", "items_required": ["cheese", "cheese"]},
        {"id": "o3", "items_required": ["cheese"]},
        {"id": "o4", "items_required": ["yogurt"]},
    ]
    # cheese at (5,2) and yogurt at (5,4) — equidistant from bot at (4,3)
    items = [
        {"id": "i1", "type": "cheese", "position": [5, 2]},
        {"id": "i2", "type": "yogurt", "position": [5, 4]},
    ]
    bots = [{"id": 0, "position": [4, 3], "inventory": []}]
    orders = [_active_order(["cheese"]), _preview_order(["yogurt"])]

    p = _make_oracle_planner(bots=bots, items=items, orders=orders, future_orders=future)
    # cheese has higher oracle demand (3 vs 1)
    assert p.oracle_item_value.get("cheese", 0) > p.oracle_item_value.get("yogurt", 0)


def test_oracle_idle_target_returns_centroid():
    """_oracle_idle_target returns centroid of items for order N+2."""
    future = [
        {"id": "o0", "items_required": ["milk"]},
        {"id": "o1", "items_required": ["bread"]},
        {"id": "o2", "items_required": ["cheese", "yogurt"]},
    ]
    items = [
        {"id": "i1", "type": "milk", "position": [3, 2]},
        {"id": "i2", "type": "bread", "position": [3, 4]},
        {"id": "i3", "type": "cheese", "position": [5, 2]},
        {"id": "i4", "type": "yogurt", "position": [5, 6]},
    ]
    bots = [{"id": 0, "position": [2, 2], "inventory": []}]
    orders = [_active_order(["milk"]), _preview_order(["bread"])]

    p = _make_oracle_planner(bots=bots, items=items, orders=orders, future_orders=future)
    target = p._oracle_idle_target(0)
    assert target is not None
    # Centroid of cheese(5,2) and yogurt(5,6) = (5, 4)
    assert target == (5, 4)


def test_oracle_idle_target_none_without_knowledge():
    """_oracle_idle_target returns None without oracle orders."""
    items = [{"id": "i1", "type": "milk", "position": [3, 2]}]
    bots = [{"id": 0, "position": [2, 2], "inventory": []}]
    orders = [_active_order(["milk"])]

    p = _make_oracle_planner(bots=bots, items=items, orders=orders)
    assert p._oracle_idle_target(0) is None


def test_clear_nonactive_holds_oracle_valuable_items():
    """Bot holds non-active items that are valuable for future orders."""
    future = [
        {"id": "o0", "items_required": ["milk"]},
        {"id": "o1", "items_required": ["bread"]},
        {"id": "o2", "items_required": ["yogurt"]},
    ]
    items = [
        {"id": "i1", "type": "milk", "position": [3, 2]},
        {"id": "i2", "type": "bread", "position": [3, 4]},
        {"id": "i3", "type": "yogurt", "position": [5, 2]},
    ]
    bots = [{"id": 0, "position": [4, 4], "inventory": ["yogurt"]}]
    orders = [_active_order(["milk"]), _preview_order(["bread"])]

    p = _make_oracle_planner(bots=bots, items=items, orders=orders, future_orders=future)
    # yogurt is in oracle_needs (order o2)
    assert "yogurt" in p.oracle_needs
    assert p.oracle_item_value.get("yogurt", 0) > 0
