"""Tests for OracleEnhancedPlanner — deep oracle lookahead."""

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
    """Oracle enhanced planner looks further ahead than base (6 vs 2)."""
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
        for i, t in enumerate(
            ["milk", "bread", "cheese", "yogurt", "butter", "eggs"], start=1
        )
    ]
    bots = [{"id": 0, "position": [2, 1], "inventory": []}]
    orders = [_active_order(["milk"]), _preview_order(["bread"])]

    p = _make_oracle_planner(
        bots=bots, items=items, orders=orders, future_orders=future
    )
    # Deep lookahead: orders N+2 through N+7 (6 ahead)
    assert "cheese" in p.oracle_needs
    assert "yogurt" in p.oracle_needs
    assert "butter" in p.oracle_needs
    assert "eggs" in p.oracle_needs


def test_oracle_needs_empty_without_knowledge():
    """oracle_needs is empty when no future orders available."""
    items = [{"id": "i1", "type": "milk", "position": [3, 2]}]
    bots = [{"id": 0, "position": [2, 2], "inventory": []}]
    orders = [_active_order(["milk"])]

    p = _make_oracle_planner(bots=bots, items=items, orders=orders)
    assert p.oracle_needs == {}


def test_oracle_needs_includes_synthetic_orders():
    """Oracle uses all orders including synthetic padding."""
    future = [
        {"id": "o0", "items_required": ["milk"]},
        {"id": "o1", "items_required": ["bread"]},
        {"id": "o2", "items_required": ["cheese"]},
        {"id": "o3", "items_required": ["yogurt"]},
    ]
    items = [
        {"id": "i1", "type": "milk", "position": [3, 2]},
        {"id": "i2", "type": "cheese", "position": [3, 4]},
        {"id": "i3", "type": "yogurt", "position": [3, 6]},
    ]
    bots = [{"id": 0, "position": [2, 2], "inventory": []}]
    orders = [_active_order(["milk"]), _preview_order(["bread"])]

    state = make_state(bots=bots, items=items, orders=orders)
    bot.reset_state()
    bot.decide_actions(state)
    gs = bot._gs
    # Set recorded_count=2 but provide 4 total (simulating synthetic padding)
    gs.set_future_orders(future, recorded_count=2)
    gs.update_demand(0)
    planner = OracleEnhancedPlanner(gs, state, full_state=state)
    planner.plan()
    # Should see orders o2 and o3 (beyond preview), even though recorded=2
    assert "cheese" in planner.oracle_needs
    assert "yogurt" in planner.oracle_needs


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

    p = _make_oracle_planner(
        bots=bots, items=items, orders=orders, future_orders=future
    )
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


def test_oracle_needs_count_reflects_frequency():
    """Items needed by multiple future orders get higher counts."""
    future = [
        {"id": "o0", "items_required": ["milk"]},
        {"id": "o1", "items_required": ["bread"]},
        {"id": "o2", "items_required": ["cheese", "milk"]},
        {"id": "o3", "items_required": ["milk", "cheese"]},
    ]
    items = [
        {"id": "i1", "type": "milk", "position": [3, 2]},
        {"id": "i2", "type": "cheese", "position": [3, 4]},
    ]
    bots = [{"id": 0, "position": [2, 2], "inventory": []}]
    orders = [_active_order(["milk"]), _preview_order(["bread"])]

    p = _make_oracle_planner(
        bots=bots, items=items, orders=orders, future_orders=future
    )
    # milk in o2 and o3 = 2, cheese in o2 and o3 = 2
    assert p.oracle_needs.get("milk", 0) == 2
    assert p.oracle_needs.get("cheese", 0) == 2
