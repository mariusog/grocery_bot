"""Tests for bot._validate_actions — drop_off penalty prevention."""

import bot
from tests.conftest import make_state


def _init_and_validate(state, actions):
    """Initialize bot state and run _validate_actions."""
    bot.reset_state()
    bot.init_static(state)
    return bot._validate_actions(actions, state)


def _make_dropoff_state(
    bot_pos=(1, 8),
    inventory=None,
    active_items=None,
    delivered=None,
):
    """Helper: state with one bot, one active order, on/near drop_off."""
    if inventory is None:
        inventory = ["milk"]
    if active_items is None:
        active_items = ["milk", "bread"]
    if delivered is None:
        delivered = []
    return make_state(
        bots=[{"id": 0, "position": list(bot_pos), "inventory": inventory}],
        items=[{"id": "item_0", "type": "milk", "position": [2, 1]}],
        orders=[
            {
                "id": "o1",
                "items_required": active_items,
                "items_delivered": delivered,
                "complete": False,
                "status": "active",
            },
        ],
    )


# ---- drop_off validation (penalty-causing) ----


def test_dropoff_valid_matching_items():
    """drop_off with matching items should pass through."""
    state = _make_dropoff_state(bot_pos=(1, 8), inventory=["milk"])
    actions = [{"bot": 0, "action": "drop_off"}]
    result = _init_and_validate(state, actions)
    assert result[0]["action"] == "drop_off"


def test_dropoff_blocked_no_matching_items():
    """drop_off when no inventory items match active order → wait."""
    state = _make_dropoff_state(bot_pos=(1, 8), inventory=["cheese"])
    actions = [{"bot": 0, "action": "drop_off"}]
    result = _init_and_validate(state, actions)
    assert result[0]["action"] == "wait"


def test_dropoff_blocked_empty_inventory():
    """drop_off with empty inventory → wait."""
    state = _make_dropoff_state(bot_pos=(1, 8), inventory=[])
    actions = [{"bot": 0, "action": "drop_off"}]
    result = _init_and_validate(state, actions)
    assert result[0]["action"] == "wait"


def test_dropoff_blocked_not_on_zone():
    """drop_off when bot is not on a drop_off zone → wait."""
    state = _make_dropoff_state(bot_pos=(5, 5), inventory=["milk"])
    actions = [{"bot": 0, "action": "drop_off"}]
    result = _init_and_validate(state, actions)
    assert result[0]["action"] == "wait"


def test_dropoff_blocked_all_items_already_delivered():
    """drop_off when active order is fully delivered → wait (empty needed)."""
    state = _make_dropoff_state(
        bot_pos=(1, 8),
        inventory=["milk"],
        active_items=["milk", "bread"],
        delivered=["milk", "bread"],
    )
    actions = [{"bot": 0, "action": "drop_off"}]
    result = _init_and_validate(state, actions)
    assert result[0]["action"] == "wait"


# ---- moves should NOT be blocked by validator ----


def test_move_into_occupied_cell_passes_through():
    """Moves into occupied cells should pass — server treats as wait, no penalty."""
    state = make_state(
        bots=[
            {"id": 0, "position": [3, 3], "inventory": []},
            {"id": 1, "position": [4, 3], "inventory": []},
        ],
        items=[{"id": "item_0", "type": "milk", "position": [2, 1]}],
        orders=[
            {
                "id": "o1",
                "items_required": ["milk"],
                "items_delivered": [],
                "complete": False,
                "status": "active",
            },
        ],
    )
    actions = [
        {"bot": 0, "action": "move_right"},  # (3,3) → (4,3) where bot 1 sits
        {"bot": 1, "action": "wait"},
    ]
    result = _init_and_validate(state, actions)
    # Validator should NOT block this move — let the server handle it
    assert result[0]["action"] == "move_right"


def test_move_into_wall_passes_through():
    """Moves into walls should pass — server treats as wait, no penalty."""
    state = make_state(
        bots=[{"id": 0, "position": [1, 1], "inventory": []}],
        items=[{"id": "item_0", "type": "milk", "position": [2, 1]}],
        walls=[[0, 1]],
        orders=[
            {
                "id": "o1",
                "items_required": ["milk"],
                "items_delivered": [],
                "complete": False,
                "status": "active",
            },
        ],
    )
    actions = [{"bot": 0, "action": "move_left"}]  # (1,1) → (0,1) which is a wall
    result = _init_and_validate(state, actions)
    assert result[0]["action"] == "move_left"


def test_pickup_passes_through():
    """Pick_up actions should pass through — no penalty for invalid pickups."""
    state = make_state(
        bots=[{"id": 0, "position": [3, 3], "inventory": []}],
        items=[{"id": "item_0", "type": "milk", "position": [2, 1]}],
        orders=[
            {
                "id": "o1",
                "items_required": ["milk"],
                "items_delivered": [],
                "complete": False,
                "status": "active",
            },
        ],
    )
    # item_0 is NOT adjacent (distance > 1), but validator should not block it
    actions = [{"bot": 0, "action": "pick_up", "item_id": "item_0"}]
    result = _init_and_validate(state, actions)
    assert result[0]["action"] == "pick_up"


def test_multiple_bots_dropoff_mixed():
    """Multi-bot: valid drop_off passes, invalid drop_off blocked, moves pass."""
    state = make_state(
        bots=[
            {"id": 0, "position": [1, 8], "inventory": ["milk"]},
            {"id": 1, "position": [1, 8], "inventory": ["cheese"]},
            {"id": 2, "position": [3, 3], "inventory": []},
        ],
        items=[{"id": "item_0", "type": "milk", "position": [2, 1]}],
        orders=[
            {
                "id": "o1",
                "items_required": ["milk"],
                "items_delivered": [],
                "complete": False,
                "status": "active",
            },
        ],
    )
    actions = [
        {"bot": 0, "action": "drop_off"},      # valid: has milk, matching active
        {"bot": 1, "action": "drop_off"},      # invalid: cheese doesn't match
        {"bot": 2, "action": "move_right"},    # move: always passes
    ]
    result = _init_and_validate(state, actions)
    assert result[0]["action"] == "drop_off"
    assert result[1]["action"] == "wait"       # blocked: no matching items
    assert result[2]["action"] == "move_right"  # passes through


def test_dropoff_with_drop_off_zones():
    """Validate drop_off against drop_off_zones when present."""
    state = make_state(
        bots=[{"id": 0, "position": [5, 5], "inventory": ["milk"]}],
        items=[{"id": "item_0", "type": "milk", "position": [2, 1]}],
        orders=[
            {
                "id": "o1",
                "items_required": ["milk"],
                "items_delivered": [],
                "complete": False,
                "status": "active",
            },
        ],
    )
    state["drop_off_zones"] = [[1, 8], [5, 5], [9, 8]]
    actions = [{"bot": 0, "action": "drop_off"}]
    result = _init_and_validate(state, actions)
    assert result[0]["action"] == "drop_off"  # (5,5) is in drop_off_zones
