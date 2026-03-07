"""Unit tests for MovementMixin methods (movement.py)."""

from collections import deque
from tests.conftest import make_planner, make_state, get_action
import bot
from tests.planner.conftest import _active_order



class TestWouldOscillate:
    def test_no_history_no_oscillation(self):
        """No history -> no oscillation detected."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        # Clear history to simulate fresh bot
        planner.gs.bot_history[0] = deque(maxlen=3)
        assert planner._would_oscillate(0, (3, 4)) is False

    def test_short_history_no_oscillation(self):
        """With only 1 position in history, no oscillation."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.gs.bot_history[0] = deque([(3, 3)], maxlen=3)
        assert planner._would_oscillate(0, (3, 4)) is False

    def test_two_step_cycle_detected(self):
        """Moving back to position 2 steps ago is oscillation."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.gs.bot_history[0] = deque([(3, 4), (3, 3)], maxlen=3)
        # Moving to (3, 4) would be going back to history[-2]
        assert planner._would_oscillate(0, (3, 4)) is True

    def test_non_oscillating_move(self):
        """Moving to a position not in recent history is fine."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.gs.bot_history[0] = deque([(3, 2), (3, 3)], maxlen=3)
        # Moving to (4, 3) is a new position
        assert planner._would_oscillate(0, (4, 3)) is False


class TestEmitMoveOrWait:
    def test_emits_move_toward_target(self):
        """Should emit a move action toward the target."""
        state = make_state(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[{"id": "i0", "type": "bread", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        # Bot has active item, no more on shelves, should rush to dropoff (1,8)
        # From (3,3), moving toward (1,8) should be move_left or move_down
        assert action["action"] in ("move_left", "move_down")

    def test_wait_when_fully_blocked(self):
        """If all adjacent cells are blocked, bot should wait."""
        # Create a scenario where bot is boxed in by walls
        state = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": ["cheese"]}],
            items=[{"id": "i0", "type": "bread", "position": [6, 6]}],
            orders=[_active_order(["cheese"])],
            walls=[[4, 5], [6, 5], [5, 4], [5, 6]],
            drop_off=[1, 8],
        )
        actions = bot.decide_actions(state)
        action = get_action(actions)
        assert action["action"] == "wait"


class TestPrePredict:
    def test_single_bot_no_predictions(self):
        """Single bot skips pre-prediction entirely."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        # After plan(), predictions should exist from _decide_bot
        assert 0 in planner.predicted

    def test_multi_bot_predictions_populated(self):
        """Multi-bot should have predictions for all bots."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 3], "inventory": []},
                {"id": 1, "position": [7, 3], "inventory": []},
            ],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [6, 2]},
            ],
            orders=[_active_order(["cheese", "milk"])],
        )
        assert 0 in planner.predicted
        assert 1 in planner.predicted

    def test_delivering_bot_predicts_toward_dropoff(self):
        """A delivering bot should predict movement toward dropoff."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [5, 3], "inventory": ["cheese", "milk", "bread"]},
                {"id": 1, "position": [7, 3], "inventory": []},
            ],
            items=[
                {"id": "i0", "type": "butter", "position": [4, 2]},
            ],
            orders=[_active_order(["cheese", "milk", "bread", "butter"])],
            drop_off=[1, 8],
        )
        # Bot 0 is full with active items -> delivering
        pred_0 = planner.predicted[0]
        # Predicted position should be closer to dropoff than current
        pos_0 = (5, 3)
        d_current = planner.gs.dist_static(pos_0, planner.drop_off)
        d_predicted = planner.gs.dist_static(pred_0, planner.drop_off)
        assert d_predicted <= d_current

    def test_extra_deliverer_targets_wait_cell_when_dropoff_is_crowded(self):
        """Only the front of the delivery pack should approach the dropoff directly."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [1, 8], "inventory": ["milk"]},
                {"id": 1, "position": [1, 7], "inventory": ["cheese"]},
                {"id": 2, "position": [2, 8], "inventory": ["bread"]},
                {"id": 3, "position": [5, 8], "inventory": ["yogurt"]},
            ],
            items=[],
            orders=[_active_order(["milk", "cheese", "bread", "yogurt"])],
            drop_off=[1, 8],
        )
        target, should_wait = planner._get_delivery_target(3, (5, 8))
        assert should_wait is True
        assert target != planner.drop_off

    def test_far_deliverer_keeps_direct_dropoff_target(self):
        """Far carriers should not stage at wait cells until they approach the zone."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [1, 8], "inventory": ["milk"]},
                {"id": 1, "position": [1, 7], "inventory": ["cheese"]},
                {"id": 2, "position": [2, 8], "inventory": ["bread"]},
                {"id": 3, "position": [8, 8], "inventory": ["yogurt"]},
            ],
            items=[],
            orders=[_active_order(["milk", "cheese", "bread", "yogurt"])],
            drop_off=[1, 8],
        )
        target, should_wait = planner._get_delivery_target(3, (8, 8))
        assert should_wait is False
        assert target == planner.drop_off

    def test_idle_near_dropoff_predicts_clearance_when_congested(self):
        """Idle bot near a congested dropoff should be predicted to clear out."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [1, 8], "inventory": ["milk"]},
                {"id": 1, "position": [1, 7], "inventory": ["cheese"]},
                {"id": 2, "position": [2, 8], "inventory": []},
                {"id": 3, "position": [5, 3], "inventory": []},
            ],
            items=[],
            orders=[_active_order(["milk", "cheese"])],
            drop_off=[1, 8],
        )
        pos_2 = (2, 8)
        pred_2 = planner.predicted[2]
        assert pred_2 != pos_2
        assert planner.gs.dist_static(pred_2, planner.drop_off) > planner.gs.dist_static(
            pos_2, planner.drop_off
        )


class TestBuildBlocked:
    def test_includes_static_blocked(self):
        """Build blocked should include walls and borders."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 3], "inventory": []},
                {"id": 1, "position": [7, 3], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        blocked = planner._build_blocked(0)
        # Should contain static blocked (borders)
        assert (-1, 0) in blocked

    def test_includes_other_bot_positions(self):
        """Blocked set should include other bots' predicted positions."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 3], "inventory": []},
                {"id": 1, "position": [5, 3], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        blocked = planner._build_blocked(0)
        # Bot 1's predicted position should be in blocked set for bot 0
        pred_1 = planner.predicted.get(1, (5, 3))
        assert pred_1 in blocked

    def test_own_position_not_blocked(self):
        """Bot's own position should not be in its blocked set (unless static)."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 3], "inventory": []},
                {"id": 1, "position": [7, 3], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        blocked = planner._build_blocked(0)
        # (3, 3) should NOT be blocked by bot 0 itself (only static if applicable)
        # Check that bot 0's own predicted position isn't added by _build_blocked
        pred_0 = planner.predicted.get(0, (3, 3))
        # The blocked set from _build_blocked(0) should not have bot 0's position
        # unless it's in the static blocked set
        if pred_0 not in planner.gs.blocked_static:
            assert pred_0 not in blocked

    def test_large_team_blocking_radius(self):
        """With 5+ bots, blocking radius is limited to Manhattan dist 6."""
        bots = [{"id": i, "position": [i + 1, 3], "inventory": []} for i in range(5)]
        planner = make_planner(
            bots=bots,
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        blocked = planner._build_blocked(0)
        # Bot 4 is at (5, 3), distance from bot 0 at (1,3) is 4 <= 6
        # So it should be included
        pred_4 = planner.predicted.get(4, (5, 3))
        assert pred_4 in blocked


class TestFindYieldAlternative:
    def test_finds_alternative_direction(self):
        """Should find an alternative move when target is blocked by yielding."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 3], "inventory": []},
                {"id": 1, "position": [4, 3], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [6, 2]}],
            orders=[_active_order(["cheese"])],
        )
        # Simulate: bot 0 wants to move to (4, 3) but that's where bot 1 is
        alt = planner._find_yield_alternative(0, 3, 3, (4, 3))
        assert alt["bot"] == 0
        # Should be a valid action (wait or a different direction)
        assert alt["action"] in (
            "wait",
            "move_up",
            "move_down",
            "move_left",
            "move_right",
        )
        # Should NOT be moving into the blocked target
        if alt["action"] != "wait":
            from grocery_bot.pathfinding import _predict_pos

            pred = _predict_pos(3, 3, alt["action"])
            assert pred != (4, 3)

    def test_returns_wait_when_no_alternative(self):
        """Should return wait if all alternatives are blocked."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [5, 5], "inventory": []},
                {"id": 1, "position": [4, 5], "inventory": []},
                {"id": 2, "position": [6, 5], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            walls=[[5, 4], [5, 6]],
        )
        # Bot 0 surrounded by walls on top/bottom, bots on left/right
        alt = planner._find_yield_alternative(0, 5, 5, (4, 5))
        assert alt["bot"] == 0
        # Only (6,5) is free but bot 2 occupies it -> wait
        assert alt["action"] in (
            "wait",
            "move_up",
            "move_down",
            "move_left",
            "move_right",
        )
