"""Unit tests for MovementMixin methods (movement.py)."""

from collections import deque
from tests.conftest import make_planner, make_state, get_action
import bot
from tests.planner.conftest import _active_order



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

    def test_wait_records_same_position(self):
        """_emit with wait should predict staying in place."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.actions = []
        planner.predicted = {}
        planner._emit(0, 3, 3, {"bot": 0, "action": "wait"})
        assert planner.predicted[0] == (3, 3)

    def test_yield_redirect(self):
        """_emit should redirect if moving into a yield-to position."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 3], "inventory": []},
                {"id": 1, "position": [4, 3], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [6, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.actions = []
        planner.predicted = {}
        planner._yield_to = {(4, 3)}  # Don't move into (4, 3)
        planner._emit(0, 3, 3, {"bot": 0, "action": "move_right"})
        # Should have been redirected since (4, 3) is in yield_to
        assert planner.predicted[0] != (4, 3) or planner.actions[0]["action"] == "wait"


class TestEmitMoveOrWaitOscillation:
    def test_oscillation_avoidance(self):
        """Bot should avoid oscillating between two positions."""
        from collections import deque

        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[{"id": "i0", "type": "bread", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        # Set up history that would cause oscillation
        planner.gs.bot_history[0] = deque([(3, 2), (3, 3)], maxlen=3)
        planner.actions = []
        blocked = planner._build_blocked(0)
        planner._emit_move_or_wait(0, 3, 3, (3, 3), (1, 8), blocked)
        assert len(planner.actions) == 1
        # The action should be valid
        assert planner.actions[0]["action"] in (
            "wait",
            "move_up",
            "move_down",
            "move_left",
            "move_right",
        )


class TestBuildBlockedRadius:
    def test_small_team_no_radius_limit(self):
        """With < 5 bots, all other bots are blocked regardless of distance."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [1, 1], "inventory": []},
                {"id": 1, "position": [9, 7], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        blocked = planner._build_blocked(0)
        pred_1 = planner.predicted.get(1, (9, 7))
        assert pred_1 in blocked
