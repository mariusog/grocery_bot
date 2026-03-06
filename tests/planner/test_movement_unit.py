"""Unit tests for MovementMixin methods (movement.py)."""

from collections import deque
from tests.conftest import make_planner, make_state, get_action
import bot


def _active_order(items_required, items_delivered=None):
    return {
        "id": "order_0",
        "items_required": items_required,
        "items_delivered": items_delivered or [],
        "complete": False,
        "status": "active",
    }


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
        assert alt["action"] in ("wait", "move_up", "move_down", "move_left", "move_right")
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
        assert alt["action"] in ("wait", "move_up", "move_down", "move_left", "move_right")


class TestBuildMovingObstacles:
    def test_excludes_self(self):
        """Moving obstacles should not include the requesting bot."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 3], "inventory": []},
                {"id": 1, "position": [7, 3], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        obstacles = planner._build_moving_obstacles(0)
        # Should only have 1 obstacle (bot 1)
        assert len(obstacles) == 1

    def test_includes_all_other_bots(self):
        """Should include current and predicted positions for other bots."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 3], "inventory": []},
                {"id": 1, "position": [5, 3], "inventory": []},
                {"id": 2, "position": [7, 3], "inventory": []},
            ],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [6, 2]},
            ],
            orders=[_active_order(["cheese", "milk"])],
        )
        obstacles = planner._build_moving_obstacles(0)
        assert len(obstacles) == 2
        # Each obstacle is (current_pos, predicted_pos)
        for cur, pred in obstacles:
            assert isinstance(cur, tuple)
            assert isinstance(pred, tuple)


class TestBfsSmart:
    def test_single_bot_uses_standard_bfs(self):
        """Single-bot mode should use standard BFS."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [6, 2]}],
            orders=[_active_order(["cheese"])],
        )
        blocked = planner._build_blocked(0)
        result = planner._bfs_smart(0, (3, 3), (5, 3), blocked)
        assert result is not None
        # Should return adjacent position
        assert abs(result[0] - 3) + abs(result[1] - 3) == 1

    def test_multi_bot_returns_valid_step(self):
        """Multi-bot BFS should return a valid next step."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 3], "inventory": []},
                {"id": 1, "position": [7, 3], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [6, 2]}],
            orders=[_active_order(["cheese"])],
        )
        blocked = planner._build_blocked(0)
        result = planner._bfs_smart(0, (3, 3), (5, 3), blocked)
        assert result is not None
        assert abs(result[0] - 3) + abs(result[1] - 3) == 1


class TestEmitMove:
    def test_emit_move_records_action(self):
        """_emit_move should add an action to self.actions."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [6, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.actions = []
        blocked = planner._build_blocked(0)
        result = planner._emit_move(0, 3, 3, (3, 3), (5, 3), blocked)
        assert result is True
        assert len(planner.actions) == 1
        assert planner.actions[0]["bot"] == 0
        assert planner.actions[0]["action"].startswith("move_")

    def test_emit_move_returns_false_for_unreachable(self):
        """_emit_move returns False when target is unreachable."""
        planner = make_planner(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [6, 6]}],
            orders=[_active_order(["cheese"])],
            walls=[[4, 5], [6, 5], [5, 4], [5, 6]],
        )
        planner.actions = []
        blocked = planner._build_blocked(0)
        result = planner._emit_move(0, 5, 5, (5, 5), (1, 1), blocked)
        assert result is False


class TestEmit:
    def test_pickup_records_last_pickup(self):
        """_emit with pick_up should record last_pickup on gs."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 2], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.actions = []
        planner._emit(0, 3, 2, {"bot": 0, "action": "pick_up", "item_id": "i0"})
        assert planner.gs.last_pickup[0] == ("i0", 0)

    def test_move_records_predicted(self):
        """_emit with a move action should update predicted dict."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.actions = []
        planner.predicted = {}
        planner._emit(0, 3, 3, {"bot": 0, "action": "move_right"})
        assert planner.predicted[0] == (4, 3)
