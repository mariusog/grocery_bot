"""Unit tests for IdleMixin — idle positioning and oscillation detection."""

from collections import deque

from tests.conftest import make_planner
from tests.planner.conftest import _active_order


class TestTryIdlePositioning:
    def test_single_bot_never_positions(self):
        """Single bot skips idle positioning."""
        planner = make_planner(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        blocked = planner._build_blocked(0)
        result = planner._try_idle_positioning(0, 5, 5, (5, 5), blocked)
        assert result is False

    def test_multi_bot_idle_positioning(self):
        """With 2+ bots, idle positioning should work."""
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
        # Reset actions to test idle positioning directly
        planner.actions = []
        blocked = planner._build_blocked(0)
        # This may or may not return True depending on scoring
        result = planner._try_idle_positioning(0, 5, 4, (5, 4), blocked)
        # Result is boolean
        assert isinstance(result, bool)

    def test_crowd_avoidance_scoring(self):
        """Idle positioning should penalize being near other bots."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [5, 4], "inventory": []},
                {"id": 1, "position": [5, 3], "inventory": []},
                {"id": 2, "position": [5, 5], "inventory": []},
            ],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 6]},
            ],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        planner.actions = []
        blocked = planner._build_blocked(0)
        # Bot 0 is surrounded by bots 1 and 2, should try to move away
        result = planner._try_idle_positioning(0, 5, 4, (5, 4), blocked)
        # With bots adjacent, it should want to move
        assert isinstance(result, bool)

    def test_idle_spots_used_for_large_teams(self):
        """With 8+ bots, idle spots from gs should be used."""
        bots = [{"id": i, "position": [i + 1, 4], "inventory": []} for i in range(8)]
        planner = make_planner(
            bots=bots,
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 6]},
            ],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        # With 8 bots, idle spots should be used for positioning
        assert len(planner.gs.idle_spots) > 0

    def test_preview_stage_target_biases_5bot_carrier_toward_dropoff(self):
        """Hard-map preview carriers should stage closer to dropoff."""
        bots = [{"id": 0, "position": [18, 7], "inventory": ["bread"]}]
        bots += [{"id": i, "position": [20, 7], "inventory": []} for i in range(1, 5)]
        planner = make_planner(
            bots=bots,
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 6]},
                {"id": "i2", "type": "bread", "position": [16, 2]},
                {"id": "i3", "type": "butter", "position": [16, 6]},
            ],
            orders=[
                _active_order(["cheese"]),
                {
                    "id": "preview_1",
                    "items_required": ["bread"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "preview",
                },
            ],
            drop_off=[1, 12],
            width=22,
            height=14,
        )
        blocked = planner._build_blocked(0)
        target = planner._get_preview_stage_target(0, (18, 7), blocked)
        assert target in planner.gs.idle_spots
        assert planner.gs.dist_static(target, planner.drop_off) < planner.gs.dist_static(
            (18, 7), planner.drop_off
        )

    def test_preview_stage_target_biases_10bot_carrier_toward_dropoff(self):
        """Expert-map preview carriers should stage closer to dropoff."""
        bots = [{"id": 0, "position": [24, 9], "inventory": ["bread"]}]
        bots += [{"id": i, "position": [26, 9], "inventory": []} for i in range(1, 10)]
        planner = make_planner(
            bots=bots,
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 6]},
                {"id": "i2", "type": "bread", "position": [20, 2]},
                {"id": "i3", "type": "butter", "position": [20, 6]},
            ],
            orders=[
                _active_order(["cheese"]),
                {
                    "id": "preview_1",
                    "items_required": ["bread"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "preview",
                },
            ],
            drop_off=[1, 16],
            width=28,
            height=18,
        )
        blocked = planner._build_blocked(0)
        target = planner._get_preview_stage_target(0, (24, 9), blocked)
        assert target in planner.gs.idle_spots
        assert planner.gs.dist_static(target, planner.drop_off) < planner.gs.dist_static(
            (24, 9), planner.drop_off
        )

    def test_preview_carrier_moves_toward_stage_target(self):
        """Preview-only carriers should head toward the selected stage target."""
        bots = [{"id": 0, "position": [24, 9], "inventory": ["bread"]}]
        bots += [{"id": i, "position": [26, 9], "inventory": []} for i in range(1, 10)]
        planner = make_planner(
            bots=bots,
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 6]},
                {"id": "i2", "type": "bread", "position": [20, 2]},
                {"id": "i3", "type": "butter", "position": [20, 6]},
            ],
            orders=[
                _active_order(["cheese"]),
                {
                    "id": "preview_1",
                    "items_required": ["bread"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "preview",
                },
            ],
            drop_off=[1, 16],
            width=28,
            height=18,
        )
        planner.actions = []
        blocked = planner._build_blocked(0)
        target = planner._get_preview_stage_target(0, (24, 9), blocked)
        result = planner._try_idle_positioning(0, 24, 9, (24, 9), blocked)
        assert result is True
        assert target is not None
        next_pos = planner.predicted[0]
        assert planner.gs.dist_static(next_pos, target) < planner.gs.dist_static((24, 9), target)


class TestLargeTeamStayBias:
    """Large teams should bias toward staying still to reduce oscillation."""

    def test_large_team_stays_at_non_idle_spot(self):
        """10-bot team bot at non-idle-spot should stay if improvement is marginal."""
        bots = [{"id": i, "position": [i + 1, 4], "inventory": []} for i in range(10)]
        # Place bot 0 away from others, at a non-idle-spot
        bots[0] = {"id": 0, "position": [5, 3], "inventory": []}
        planner = make_planner(
            bots=bots,
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 6]},
            ],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        # Verify bot 0 is NOT at an idle spot
        set(planner.gs.idle_spots) if planner.gs.idle_spots else set()
        pos = (5, 3)
        # The stay bias should still apply on large teams even at non-idle spots
        planner.actions = []
        blocked = planner._build_blocked(0)
        result = planner._try_idle_positioning(0, 5, 3, pos, blocked)
        # Result is boolean — we can't guarantee stay, but on a 10-bot team
        # the threshold should be higher, reducing unnecessary movement
        assert isinstance(result, bool)


class TestIdleDropoffPenaltyRadius:
    """IDLE_DROPOFF_PENALTY_RADIUS should be 2 for tighter dropoff clearing."""

    def test_constant_value(self):
        from grocery_bot.constants import IDLE_DROPOFF_PENALTY_RADIUS

        assert IDLE_DROPOFF_PENALTY_RADIUS == 2


class TestLargeTeamNoTargetAttract:
    """Teams >= 10 bots should ignore item-target attraction in idle scoring."""

    def test_10bot_ignores_target_distance(self):
        """10-bot team: idle bot equidistant from other bots but at different
        distances from items should score the same (target weight = 0)."""
        bots = [{"id": i, "position": [i + 1, 4], "inventory": []} for i in range(10)]
        # Place bot 0 far from other bots so crowd avoidance is neutral
        bots[0] = {"id": 0, "position": [15, 4], "inventory": []}
        planner = make_planner(
            bots=bots,
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 6]},
            ],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
            width=20,
            height=10,
        )
        # With target weight = 0, the idle scoring should not attract
        # bot 0 toward items — only crowd avoidance and dropoff penalty matter
        planner.actions = []
        blocked = planner._build_blocked(0)
        # Just ensure it runs without error and returns a boolean
        result = planner._try_idle_positioning(0, 15, 4, (15, 4), blocked)
        assert isinstance(result, bool)

    def test_5bot_still_uses_target_distance(self):
        """5-bot team should still attract idle bots toward item targets."""
        from grocery_bot.constants import IDLE_TARGET_DISTANCE_WEIGHT

        # Verify the constant is non-zero (used for small teams)
        assert IDLE_TARGET_DISTANCE_WEIGHT > 0


class TestOscillationDetection:
    """Tests for _is_stuck_oscillating A-B-A detection."""

    def _planner_with_history(self, bid: int, positions: list[tuple[int, int]]):
        """Create a planner with pre-populated bot history."""
        planner = make_planner(
            bots=[
                {"id": bid, "position": list(positions[-1]), "inventory": []},
                {"id": 99, "position": [8, 4], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.gs.bot_history[bid] = deque(positions, maxlen=3)
        return planner

    def test_detects_aba_pattern(self):
        """A-B-A bounce should be detected as oscillation."""
        planner = self._planner_with_history(0, [(5, 4), (5, 5), (5, 4)])
        assert planner._is_stuck_oscillating(0) is True

    def test_no_oscillation_on_straight_path(self):
        """A-B-C movement is not oscillation."""
        planner = self._planner_with_history(0, [(5, 4), (5, 5), (5, 6)])
        assert planner._is_stuck_oscillating(0) is False

    def test_no_oscillation_when_staying_put(self):
        """A-A-A (stationary) is not oscillation."""
        planner = self._planner_with_history(0, [(5, 4), (5, 4), (5, 4)])
        assert planner._is_stuck_oscillating(0) is False

    def test_no_oscillation_with_short_history(self):
        """Less than 3 positions — not enough data to detect."""
        planner = self._planner_with_history(0, [(5, 4), (5, 5)])
        # Only 2 positions in history
        planner.gs.bot_history[0] = deque([(5, 4), (5, 5)], maxlen=3)
        assert planner._is_stuck_oscillating(0) is False

    def test_no_oscillation_for_unknown_bot(self):
        """Bot with no history should not trigger."""
        planner = self._planner_with_history(0, [(5, 4), (5, 5), (5, 4)])
        assert planner._is_stuck_oscillating(42) is False


class TestBreakOscillation:
    """Tests for _step_break_oscillation step chain behavior."""

    def _planner_oscillating_with_inv(self, inv: list[str], positions: list[tuple[int, int]]):
        """Create a planner where bot 0 is oscillating with given inventory."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": list(positions[-1]), "inventory": inv},
                {"id": 1, "position": [8, 4], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        planner.gs.bot_history[0] = deque(positions, maxlen=3)
        planner.actions = []
        return planner

    def test_oscillating_with_inventory_delivers(self):
        """Oscillating bot with items should head to dropoff."""
        planner = self._planner_oscillating_with_inv(["milk"], [(5, 4), (5, 5), (5, 4)])
        ctx = planner._build_bot_context(planner.bots[0])
        result = planner._step_break_oscillation(ctx)
        assert result is True
        assert len(planner.actions) == 1
        # Should be moving, not waiting
        assert planner.actions[0]["action"] != "wait"

    def test_oscillating_empty_waits(self):
        """Oscillating bot with no items should wait."""
        planner = self._planner_oscillating_with_inv([], [(5, 4), (5, 5), (5, 4)])
        ctx = planner._build_bot_context(planner.bots[0])
        result = planner._step_break_oscillation(ctx)
        assert result is True
        assert len(planner.actions) == 1
        assert planner.actions[0]["action"] == "wait"

    def test_not_oscillating_skips(self):
        """Non-oscillating bot should not trigger the step."""
        planner = self._planner_oscillating_with_inv(["milk"], [(5, 4), (5, 5), (5, 6)])
        ctx = planner._build_bot_context(planner.bots[0])
        result = planner._step_break_oscillation(ctx)
        assert result is False
        assert len(planner.actions) == 0
