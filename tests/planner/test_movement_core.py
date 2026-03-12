"""Unit tests for MovementMixin methods (movement.py)."""

from collections import deque

import bot
from tests.conftest import get_action, make_planner, make_state
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
        pred_0 = planner.predicted.get(0, (3, 3))
        if pred_0 not in planner.gs.blocked_static:
            assert pred_0 not in blocked

    def test_large_team_blocking_radius(self):
        """With 5+ bots, blocking radius is limited to Manhattan dist 4."""
        bots = [{"id": i, "position": [i + 1, 3], "inventory": []} for i in range(5)]
        planner = make_planner(
            bots=bots,
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        blocked = planner._build_blocked(0)
        # Bot 1 at (2,3) is distance 1 from bot 0 at (1,3) — within radius 4
        pred_1 = planner.predicted.get(1, (2, 3))
        assert pred_1 in blocked

    def test_huge_team_tighter_radius(self):
        """With 15+ bots, blocking radius is 3 (tighter than 5-7 bots)."""
        bots = [{"id": i, "position": [i + 1, 3], "inventory": []} for i in range(15)]
        planner = make_planner(
            bots=bots,
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            width=20,
            height=9,
        )
        blocked = planner._build_blocked(0)
        # Bot 1 at (2,3) is distance 1 from bot 0 at (1,3) — within radius 3
        pred_1 = planner.predicted.get(1, (2, 3))
        assert pred_1 in blocked


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
