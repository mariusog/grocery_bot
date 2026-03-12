"""TDD tests for WebSocket desync prevention.

These tests catch the live server bug where actions get offset by 1 round,
causing:
1. Pickup failures from position mismatch (bot not where expected)
2. Permanent blacklisting of items from transient failures
3. Score collapse (148 simulator -> 1 live)

The root cause is a race condition: the server sends the next state before
processing our actions, so our actions are applied to the wrong round.
"""

import bot
from tests.conftest import make_state

# ── Helpers ──────────────────────────────────────────────────────────────


def _standard_items():
    return [
        {"id": "item_0", "type": "butter", "position": [3, 2]},
        {"id": "item_1", "type": "yogurt", "position": [5, 2]},
        {"id": "item_2", "type": "cheese", "position": [3, 3]},
        {"id": "item_3", "type": "milk", "position": [5, 3]},
        {"id": "item_4", "type": "butter", "position": [3, 4]},
        {"id": "item_5", "type": "yogurt", "position": [5, 4]},
        {"id": "item_6", "type": "cheese", "position": [7, 2]},
        {"id": "item_7", "type": "milk", "position": [7, 3]},
    ]


def _standard_orders():
    return [
        {
            "id": "o1",
            "items_required": ["yogurt", "cheese", "butter"],
            "items_delivered": [],
            "complete": False,
            "status": "active",
        },
        {
            "id": "o2",
            "items_required": ["milk", "milk"],
            "items_delivered": [],
            "complete": False,
            "status": "preview",
        },
    ]


def _run_round(state):
    """Run decide_actions and return (actions, gs)."""
    actions = bot.decide_actions(state)
    return actions, bot._gs


# ── Test: Pickup failure from desync should NOT blacklist ────────────────


class TestDesyncPickupFailure:
    """When desync causes a pickup to 'fail', the item must not be blacklisted."""

    def test_pickup_fail_not_counted_when_position_shifted(self):
        """If bot position doesn't match expected after pickup, don't count failure.

        Scenario: Bot at (5,7) sends pick_up for item at (5,6). Due to desync,
        next state shows bot at (5,8) — the server never applied the action.
        This should NOT count as a pickup failure.
        """
        items = _standard_items()
        orders = _standard_orders()

        # Round N: bot at (5,7), sends pick_up for item_5 (yogurt at 5,4... let's use cheese)
        state1 = make_state(
            bots=[{"id": 0, "position": [4, 3], "inventory": []}],
            items=items,
            orders=orders,
        )
        _actions1, gs = _run_round(state1)

        # Simulate: bot sent pick_up for item_2 (cheese at 3,3), expected to stay at (4,3)
        # Manually set last_pickup to simulate what _emit_action does
        gs.last_pickup[0] = ("item_2", 0)
        # Record expected position
        gs.last_expected_pos = {0: (4, 3)}

        # Round N+1: desync — bot is at (5,3) instead of (4,3)
        # Inventory didn't grow because server never applied pickup
        state2 = make_state(
            bots=[{"id": 0, "position": [5, 3], "inventory": []}],
            items=items,
            orders=orders,
            round_num=1,
        )
        _run_round(state2)

        # Pickup failure should NOT be counted because position shifted
        assert gs.pickup_fail_count.get("item_2", 0) == 0, (
            "Pickup failure from desync (position mismatch) should not be counted"
        )
        assert "item_2" not in gs.blacklisted_items

    def test_genuine_pickup_fail_still_counted(self):
        """A real pickup failure (bot at correct position) should still be counted."""
        items = _standard_items()
        orders = _standard_orders()

        state1 = make_state(
            bots=[{"id": 0, "position": [4, 3], "inventory": []}],
            items=items,
            orders=orders,
        )
        _run_round(state1)
        gs = bot._gs

        # Simulate: bot sent pick_up, recorded expected position
        gs.last_pickup[0] = ("item_2", 0)
        gs.last_expected_pos = {0: (4, 3)}

        # Round N+1: bot IS at expected position, but inventory didn't grow
        # This is a genuine failure (item might be gone, etc.)
        state2 = make_state(
            bots=[{"id": 0, "position": [4, 3], "inventory": []}],
            items=items,
            orders=orders,
            round_num=1,
        )
        _run_round(state2)

        assert gs.pickup_fail_count.get("item_2", 0) >= 1, (
            "Genuine pickup failure should be counted"
        )

    def test_three_desync_fails_do_not_blacklist(self):
        """Three pickup 'failures' from desync should NOT cause blacklisting."""
        items = _standard_items()
        orders = _standard_orders()

        state0 = make_state(
            bots=[{"id": 0, "position": [4, 3], "inventory": []}],
            items=items,
            orders=orders,
        )
        _run_round(state0)
        gs = bot._gs

        # Simulate 3 rounds of desync pickup failures
        for round_num in range(1, 4):
            gs.last_pickup[0] = ("item_2", 0)
            gs.last_expected_pos = {0: (4, 3)}

            # Each round, bot position shifted (desync)
            state = make_state(
                bots=[{"id": 0, "position": [5, 3], "inventory": []}],
                items=items,
                orders=orders,
                round_num=round_num,
            )
            _run_round(state)

        assert "item_2" not in gs.blacklisted_items, (
            "Desync-caused failures should never blacklist an item"
        )


# ── Test: Blacklist expiry ──────────────────────────────────────────────


class TestBlacklistExpiry:
    """Blacklisted items should expire after a configurable number of rounds."""

    def test_blacklist_expires_after_n_rounds(self):
        """A blacklisted item should be un-blacklisted after enough rounds pass."""
        from grocery_bot.constants import BLACKLIST_EXPIRY_ROUNDS

        items = _standard_items()
        orders = _standard_orders()

        state = make_state(
            bots=[{"id": 0, "position": [1, 5], "inventory": []}],
            items=items,
            orders=orders,
        )
        _run_round(state)
        gs = bot._gs

        # Manually blacklist an item at round 0
        gs.blacklisted_items.add("item_2")
        gs.blacklist_round["item_2"] = 0

        # Run past the expiry window. Use a position far from items
        # to avoid re-triggering pickup failures.
        expiry_round = BLACKLIST_EXPIRY_ROUNDS + 1
        state = make_state(
            bots=[{"id": 0, "position": [1, 5], "inventory": []}],
            items=items,
            orders=orders,
            round_num=expiry_round,
        )
        _run_round(state)

        assert "item_2" not in gs.blacklisted_items, (
            "Blacklisted item should expire after enough rounds"
        )

    def test_blacklist_persists_within_expiry_window(self):
        """Blacklisted item should stay blacklisted within the expiry window."""
        items = _standard_items()
        orders = _standard_orders()

        state = make_state(
            bots=[{"id": 0, "position": [4, 3], "inventory": []}],
            items=items,
            orders=orders,
        )
        _run_round(state)
        gs = bot._gs

        gs.blacklisted_items.add("item_2")
        gs.blacklist_round = {"item_2": 0}

        # Run just 2 rounds — should still be blacklisted
        state = make_state(
            bots=[{"id": 0, "position": [4, 3], "inventory": []}],
            items=items,
            orders=orders,
            round_num=2,
        )
        _run_round(state)

        assert "item_2" in gs.blacklisted_items, (
            "Blacklisted item should persist within expiry window"
        )


# ── Test: Expected position tracking ────────────────────────────────────


class TestExpectedPositionTracking:
    """The bot should track expected positions after sending actions."""

    def test_move_action_sets_expected_position(self):
        """After emitting a move action, expected position should be set."""
        items = _standard_items()
        orders = _standard_orders()

        state = make_state(
            bots=[{"id": 0, "position": [5, 7], "inventory": []}],
            items=items,
            orders=orders,
        )
        actions, gs = _run_round(state)

        action = actions[0]["action"]
        if action == "move_left":
            expected = (4, 7)
        elif action == "move_right":
            expected = (6, 7)
        elif action == "move_up":
            expected = (5, 6)
        elif action == "move_down":
            expected = (5, 8)
        else:
            expected = (5, 7)

        assert hasattr(gs, "last_expected_pos"), "GameState must have last_expected_pos attribute"
        assert gs.last_expected_pos.get(0) == expected, (
            f"Expected position {expected} for action {action}, got {gs.last_expected_pos.get(0)}"
        )

    def test_pickup_action_expects_same_position(self):
        """After pick_up, expected position should be same as current."""
        items = _standard_items()
        orders = _standard_orders()

        # Bot adjacent to item, should pick_up
        state = make_state(
            bots=[{"id": 0, "position": [4, 3], "inventory": []}],
            items=items,
            orders=orders,
        )
        actions, gs = _run_round(state)

        # Find if any action is pick_up
        pickup_actions = [a for a in actions if a["action"] == "pick_up"]
        if pickup_actions:
            assert gs.last_expected_pos.get(0) == (4, 3)


# ── Test: Collision validation matches live server ──────────────────────


class TestCollisionValidation:
    """Validator only blocks penalty-causing actions (illegal drop_off)."""

    def test_move_into_occupied_cell_passes_through(self):
        """Moves into occupied cells pass through — server treats as wait, no penalty."""
        state = make_state(
            bots=[
                {"id": 0, "position": [5, 5], "inventory": []},
                {"id": 1, "position": [4, 5], "inventory": []},
            ],
            items=[],
            orders=[],
        )
        bot.init_static(state)

        validated = bot._validate_actions(
            [
                {"bot": 0, "action": "move_left"},
                {"bot": 1, "action": "move_up"},
            ],
            state,
        )

        # Validator only blocks drop_off; moves pass through to server
        assert validated == [
            {"bot": 0, "action": "move_left"},
            {"bot": 1, "action": "move_up"},
        ]


# ── Test: Round number in WebSocket response ────────────────────────────


class TestRoundInResponse:
    """The bot should include round number in its WebSocket response."""

    def test_decide_actions_returns_round_number(self):
        """decide_actions should return actions with round info for tagging.

        The WebSocket loop should send {"round": N, "actions": [...]} to
        help the server match actions to the correct round.
        """
        items = _standard_items()
        orders = _standard_orders()

        state = make_state(
            bots=[{"id": 0, "position": [5, 7], "inventory": []}],
            items=items,
            orders=orders,
            round_num=42,
        )

        # After decide_actions, the GameState should know the last round processed
        bot.decide_actions(state)
        gs = bot._gs
        assert hasattr(gs, "last_round_processed"), "GameState must track last_round_processed"
        assert gs.last_round_processed == 42


# ── Test: Full desync simulation ────────────────────────────────────────


class TestFullDesyncSimulation:
    """Simulate a full desync sequence like the live games."""

    def test_desync_after_dropoff_does_not_destroy_state(self):
        """Reproduce game 1: desync starts after first drop_off at round 37.

        After drop_off, the server's next state doesn't reflect the drop.
        The bot should NOT permanently blacklist items or get stuck.
        """
        items = _standard_items()
        orders = _standard_orders()

        # Round 0: Initialize
        state0 = make_state(
            bots=[{"id": 0, "position": [1, 8], "inventory": ["cheese", "yogurt", "butter"]}],
            items=items,
            orders=orders,
        )
        actions0, gs = _run_round(state0)

        # Expect drop_off action
        assert actions0[0]["action"] == "drop_off"
        gs.last_expected_pos = {0: (1, 8)}

        # Round 1: Server processed drop_off, inventory cleared, score updated
        state1 = make_state(
            bots=[{"id": 0, "position": [1, 8], "inventory": []}],
            items=items,
            orders=[
                {
                    "id": "o2",
                    "items_required": ["milk", "milk"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            round_num=1,
            score=8,
        )
        actions1, gs = _run_round(state1)

        # Bot should be moving toward items, not stuck
        assert actions1[0]["action"].startswith("move_"), (
            f"After drop_off, bot should move toward items, got {actions1[0]['action']}"
        )

        # Simulate desync: bot sent move_right, but server says bot is still at (1,8)
        state2 = make_state(
            bots=[{"id": 0, "position": [1, 8], "inventory": []}],
            items=items,
            orders=[
                {
                    "id": "o2",
                    "items_required": ["milk", "milk"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
            ],
            round_num=2,
            score=8,
        )
        actions2, gs = _run_round(state2)

        # Bot should still function — it uses server state, not cached expected
        assert actions2[0]["action"] != "wait", "Bot should not get stuck after desync"

        # No items should be blacklisted from this sequence
        assert len(gs.blacklisted_items) == 0, (
            f"No items should be blacklisted from desync: {gs.blacklisted_items}"
        )

    def test_repeated_pickup_desync_does_not_blacklist(self):
        """Reproduce the exact failure mode: bot tries pick_up 3 times,
        each time desync prevents it, and the item gets wrongly blacklisted.
        """
        items = _standard_items()
        orders = _standard_orders()

        state0 = make_state(
            bots=[{"id": 0, "position": [4, 3], "inventory": []}],
            items=items,
            orders=orders,
        )
        _run_round(state0)
        gs = bot._gs

        item_id = "item_2"  # cheese at (3,3)

        for r in range(1, 5):
            # Bot thinks it's adjacent and sends pick_up
            gs.last_pickup[0] = (item_id, 0)
            gs.last_expected_pos = {0: (4, 3)}

            # Server says bot is at wrong position (desync)
            desync_pos = [5, 3] if r % 2 == 0 else [3, 3]
            state = make_state(
                bots=[{"id": 0, "position": desync_pos, "inventory": []}],
                items=items,
                orders=orders,
                round_num=r,
            )
            _run_round(state)

        assert item_id not in gs.blacklisted_items, (
            f"{item_id} was blacklisted due to desync pickup failures"
        )
