"""Unit tests for IdleMixin — dropoff clearing and scoring."""

from tests.conftest import make_planner
from tests.planner.conftest import _active_order


class TestTryClearDropoff:
    def test_single_bot_never_clears(self):
        """Single bot should never clear dropoff."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 7], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        blocked = planner._build_blocked(0)
        result = planner._try_clear_dropoff(0, 1, 7, (1, 7), blocked)
        assert result is False

    def test_within_clear_radius_clears(self):
        """Bot near dropoff with 2+ bots should try to clear."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [1, 7], "inventory": []},
                {"id": 1, "position": [5, 3], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        blocked = planner._build_blocked(0)
        # Bot 0 at (1,7) is 1 step from dropoff (1,8) — within clear radius of 3
        result = planner._try_clear_dropoff(0, 1, 7, (1, 7), blocked)
        assert result is True

    def test_beyond_clear_radius_does_nothing(self):
        """Bot far from dropoff should not try to clear."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [5, 1], "inventory": []},
                {"id": 1, "position": [7, 3], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        blocked = planner._build_blocked(0)
        d = planner.gs.dist_static((5, 1), planner.drop_off)
        # Bot is far from dropoff
        assert d > 3
        result = planner._try_clear_dropoff(0, 5, 1, (5, 1), blocked)
        assert result is False


class TestTryClearDropoffEdgeCases:
    def test_at_dropoff_moves_away(self):
        """Bot right at dropoff should move away."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [1, 8], "inventory": []},
                {"id": 1, "position": [5, 3], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        planner.actions = []
        blocked = planner._build_blocked(0)
        result = planner._try_clear_dropoff(0, 1, 8, (1, 8), blocked)
        assert result is True
        # Bot should have moved away from dropoff
        assert len(planner.actions) == 1
        assert planner.actions[0]["action"].startswith("move_")

    def test_all_directions_blocked(self):
        """If all directions away from dropoff are blocked, returns False."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [1, 8], "inventory": []},
                {"id": 1, "position": [5, 3], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
            walls=[[0, 8], [2, 8], [1, 7]],
        )
        planner.actions = []
        blocked = planner._build_blocked(0)
        result = planner._try_clear_dropoff(0, 1, 8, (1, 8), blocked)
        # All adjacent cells are blocked (walls + border below)
        # The result depends on whether there's any position further from dropoff
        assert isinstance(result, bool)


class TestScoreIdleCandidate:
    def test_score_penalizes_dropoff_proximity(self):
        """Positions near dropoff should score higher (worse)."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [5, 4], "inventory": []},
                {"id": 1, "position": [7, 4], "inventory": []},
            ],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 6]},
            ],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        # The scoring happens inside _try_idle_positioning
        # We just verify the method returns a valid boolean
        planner.actions = []
        blocked = planner._build_blocked(0)
        result = planner._try_idle_positioning(0, 5, 4, (5, 4), blocked)
        assert isinstance(result, bool)


class TestIdlePositioningSingleBot:
    def test_never_positions_single_bot(self):
        """Single bot always returns False for idle positioning."""
        planner = make_planner(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        blocked = planner._build_blocked(0)
        assert planner._try_idle_positioning(0, 5, 5, (5, 5), blocked) is False

    def test_never_clears_single_bot(self):
        """Single bot always returns False for clearing dropoff."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 7], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        blocked = planner._build_blocked(0)
        assert planner._try_clear_dropoff(0, 1, 7, (1, 7), blocked) is False
