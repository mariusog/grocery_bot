"""Tests for convergence collision detection in _emit.

Convergence collision: two bots both target the same empty cell.
The server rejects one bot's move, causing a desync. The planner
must detect this in _emit and redirect the second bot.
"""

from tests.conftest import make_planner
from tests.planner.conftest import _active_order


def _setup_two_bot_convergence():
    """Create a planner where two bots will converge on the same cell.

    Layout (11x9, dropoff at 1,8):
      Bot 0 at (3, 4) — will want to move right toward item
      Bot 1 at (5, 4) — will want to move left toward item
      Item at (4, 3) — adjacent cell (4, 4) is the convergence point
    """
    planner = make_planner(
        bots=[
            {"id": 0, "position": [3, 4], "inventory": []},
            {"id": 1, "position": [5, 4], "inventory": []},
        ],
        items=[{"id": "i0", "type": "cheese", "position": [4, 3]}],
        orders=[_active_order(["cheese"])],
    )
    return planner


class TestConvergenceDetection:
    """_emit must prevent two decided bots from targeting the same cell."""

    def test_second_bot_redirected_on_convergence(self):
        """When bot 0 already decided to move to (4,4), bot 1 must not also go there."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 4], "inventory": []},
                {"id": 1, "position": [5, 4], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 3]}],
            orders=[_active_order(["cheese"])],
        )
        # Reset planner state to manually control emit sequence
        planner.actions = []
        planner.predicted = {}
        planner._decided = set()

        # Bot 0 decides to move right to (4, 4)
        planner._emit(0, 3, 4, {"bot": 0, "action": "move_right"})
        assert planner.predicted[0] == (4, 4)

        # Bot 1 tries to move left to (4, 4) — same cell!
        planner._emit(1, 5, 4, {"bot": 1, "action": "move_left"})

        # Bot 1 must NOT end up targeting (4, 4)
        assert planner.predicted[1] != (4, 4), (
            "Convergence collision: bot 1 targets same cell as bot 0"
        )

    def test_first_bot_keeps_its_target(self):
        """The first bot to decide keeps its target; only later bots redirect."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 4], "inventory": []},
                {"id": 1, "position": [5, 4], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 3]}],
            orders=[_active_order(["cheese"])],
        )
        planner.actions = []
        planner.predicted = {}
        planner._decided = set()

        planner._emit(0, 3, 4, {"bot": 0, "action": "move_right"})
        assert planner.predicted[0] == (4, 4)

        planner._emit(1, 5, 4, {"bot": 1, "action": "move_left"})
        # Bot 0 must still target (4, 4)
        assert planner.predicted[0] == (4, 4)

    def test_convergence_redirects_to_valid_cell(self):
        """Redirected bot should end up at a valid, unoccupied cell."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 4], "inventory": []},
                {"id": 1, "position": [5, 4], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 3]}],
            orders=[_active_order(["cheese"])],
        )
        planner.actions = []
        planner.predicted = {}
        planner._decided = set()

        planner._emit(0, 3, 4, {"bot": 0, "action": "move_right"})
        planner._emit(1, 5, 4, {"bot": 1, "action": "move_left"})

        pred_1 = planner.predicted[1]
        # Must not collide with bot 0's target
        assert pred_1 != planner.predicted[0]
        # Must not be a wall
        assert pred_1 not in planner.gs.blocked_static

    def test_three_bot_convergence(self):
        """Three bots targeting the same cell: only first gets it."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 4], "inventory": []},
                {"id": 1, "position": [5, 4], "inventory": []},
                {"id": 2, "position": [4, 5], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 3]}],
            orders=[_active_order(["cheese"])],
        )
        planner.actions = []
        planner.predicted = {}
        planner._decided = set()

        # All three bots try to reach (4, 4)
        planner._emit(0, 3, 4, {"bot": 0, "action": "move_right"})
        planner._emit(1, 5, 4, {"bot": 1, "action": "move_left"})
        planner._emit(2, 4, 5, {"bot": 2, "action": "move_up"})

        # All three must have different predicted positions
        preds = [planner.predicted[i] for i in range(3)]
        assert len(set(preds)) == 3, f"Duplicate predictions: {preds}"
        # Bot 0 keeps (4, 4)
        assert planner.predicted[0] == (4, 4)


class TestNoFalsePositives:
    """Convergence check must not interfere with valid moves."""

    def test_non_conflicting_moves_unchanged(self):
        """Bots moving to different cells should not be redirected."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 4], "inventory": []},
                {"id": 1, "position": [5, 4], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 3]}],
            orders=[_active_order(["cheese"])],
        )
        planner.actions = []
        planner.predicted = {}
        planner._decided = set()

        # Bot 0 moves right to (4, 4), bot 1 moves right to (6, 4)
        planner._emit(0, 3, 4, {"bot": 0, "action": "move_right"})
        planner._emit(1, 5, 4, {"bot": 1, "action": "move_right"})

        assert planner.predicted[0] == (4, 4)
        assert planner.predicted[1] == (6, 4)

    def test_pickup_actions_not_affected(self):
        """Pick_up actions don't have convergence issues."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 4], "inventory": []},
                {"id": 1, "position": [5, 4], "inventory": []},
            ],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 4]},
                {"id": "i1", "type": "bread", "position": [6, 4]},
            ],
            orders=[_active_order(["cheese", "bread"])],
        )
        planner.actions = []
        planner.predicted = {}
        planner._decided = set()

        # Both bots pick up (no movement conflict)
        planner._emit(0, 3, 4, {"bot": 0, "action": "pick_up", "item_id": "i0"})
        planner._emit(1, 5, 4, {"bot": 1, "action": "pick_up", "item_id": "i1"})

        # Both should stay at their positions
        assert planner.predicted[0] == (3, 4)
        assert planner.predicted[1] == (5, 4)

    def test_undecided_bot_prediction_not_checked(self):
        """Pre-predicted positions from undecided bots should NOT trigger redirect.

        Only already-decided bots (in self._decided) should cause convergence
        redirects. Pre-predictions are estimates and get overwritten.
        """
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 4], "inventory": []},
                {"id": 1, "position": [5, 4], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 3]}],
            orders=[_active_order(["cheese"])],
        )
        planner.actions = []
        planner._decided = set()
        # Simulate pre-predict: bot 1 predicted at (4, 4) but NOT decided yet
        planner.predicted = {1: (4, 4)}

        # Bot 0 should still be able to move to (4, 4) since bot 1 hasn't decided
        planner._emit(0, 3, 4, {"bot": 0, "action": "move_right"})
        assert planner.predicted[0] == (4, 4)


class TestFullPlanConvergence:
    """Integration: full plan() must not produce convergent actions."""

    def test_no_duplicate_predictions_after_plan(self):
        """After plan(), no two bots should have the same predicted position."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 4], "inventory": []},
                {"id": 1, "position": [5, 4], "inventory": []},
                {"id": 2, "position": [7, 4], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 3]}],
            orders=[_active_order(["cheese"])],
        )
        # Check that all predicted positions are unique
        preds = list(planner.predicted.values())
        assert len(preds) == len(set(preds)), (
            f"Duplicate predicted positions after plan(): {planner.predicted}"
        )

    def test_no_duplicate_predictions_large_team(self):
        """10-bot team must not have convergent predicted positions."""
        bots = [{"id": i, "position": [2 + i, 4], "inventory": []} for i in range(10)]
        planner = make_planner(
            bots=bots,
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 3]},
                {"id": "i1", "type": "bread", "position": [6, 3]},
            ],
            orders=[_active_order(["cheese", "bread"])],
            width=20,
            height=9,
        )
        preds = list(planner.predicted.values())
        assert len(preds) == len(set(preds)), (
            f"Duplicate predicted positions in 10-bot plan: {planner.predicted}"
        )
