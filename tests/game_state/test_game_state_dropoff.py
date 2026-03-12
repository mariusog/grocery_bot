"""Unit tests for GameState methods (game_state.py)."""

from tests.conftest import make_gs_with_state
from tests.game_state.conftest import _make_gs_with_dropoff


class TestPrecomputeDropoffZones:
    def test_dropoff_adjacents_populated(self):
        gs = _make_gs_with_dropoff()
        assert len(gs.dropoff_adjacents) > 0

    def test_dropoff_adjacents_are_walkable(self):
        gs = _make_gs_with_dropoff()
        for adj in gs.dropoff_adjacents:
            assert adj not in gs.blocked_static

    def test_dropoff_approach_cells_within_radius(self):
        from grocery_bot.game_state import DROPOFF_CONGESTION_RADIUS

        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        for cell in gs.dropoff_approach_cells:
            d = gs.dist_static(cell, drop_off)
            assert 0 < d <= DROPOFF_CONGESTION_RADIUS

    def test_dropoff_approach_set_matches_list(self):
        gs = _make_gs_with_dropoff()
        # approach_set includes the dropoff itself plus all approach cells
        expected = set(gs.dropoff_approach_cells) | {gs.drop_off_pos}
        assert gs.dropoff_approach_set == expected

    def test_dropoff_wait_cells_at_correct_distance(self):
        from grocery_bot.game_state import DROPOFF_WAIT_DISTANCE

        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        for cell in gs.dropoff_wait_cells:
            d = gs.dist_static(cell, drop_off)
            assert d == DROPOFF_WAIT_DISTANCE

    def test_dropoff_zones_empty_without_drop_off_key(self):
        """When state has no drop_off key, zones are not computed."""
        gs = make_gs_with_state()
        assert gs.dropoff_adjacents == []
        assert gs.dropoff_approach_cells == []
        assert gs.dropoff_wait_cells == []

    def test_walled_dropoff_has_fewer_adjacents(self):
        """Dropoff surrounded by walls on 2 sides has fewer adjacents."""
        # Drop_off at (1, 8), wall at (0, 8) and (2, 8)
        gs = _make_gs_with_dropoff(walls=[[0, 8], [2, 8]])
        # Only vertical neighbors could be adjacent
        for adj in gs.dropoff_adjacents:
            assert adj not in {(0, 8), (2, 8)}


class TestGetDropoffApproachTarget:
    def test_closest_bot_goes_directly(self):
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        delivering = [(0, (1, 7)), (1, (5, 5))]
        target, should_wait = gs.get_dropoff_approach_target(0, (1, 7), drop_off, delivering)
        assert target == drop_off
        assert should_wait is False

    def test_far_bot_gets_wait_target(self):
        from grocery_bot.game_state import MAX_APPROACH_SLOTS

        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        # Create enough closer bots to fill approach slots
        delivering = [(i, (1, 8 - i - 1)) for i in range(MAX_APPROACH_SLOTS + 1)]
        far_id = MAX_APPROACH_SLOTS
        far_pos = delivering[far_id][1]
        target, should_wait = gs.get_dropoff_approach_target(far_id, far_pos, drop_off, delivering)
        assert should_wait is True
        assert target != drop_off

    def test_already_at_dropoff_goes_directly(self):
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        # Only bot delivering -- should go directly
        delivering = [(0, (1, 7))]
        target, should_wait = gs.get_dropoff_approach_target(0, (1, 7), drop_off, delivering)
        assert target == drop_off
        assert should_wait is False

    def test_no_approach_cells_returns_dropoff(self):
        """When approach cells are empty, always returns dropoff."""
        gs = _make_gs_with_dropoff()
        gs.dropoff_approach_cells = []
        drop_off = (1, 8)
        target, should_wait = gs.get_dropoff_approach_target(0, (5, 5), drop_off, [(0, (5, 5))])
        assert target == drop_off
        assert should_wait is False

    def test_tiebreak_by_bot_id(self):
        """When two bots are equidistant, lower bot_id gets priority."""
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        # Both bots at same distance from dropoff
        delivering = [(0, (1, 6)), (1, (1, 6)), (2, (1, 6))]
        # Bot 0 and 1 should go directly (MAX_APPROACH_SLOTS=2)
        _, wait_0 = gs.get_dropoff_approach_target(0, (1, 6), drop_off, delivering)
        _, wait_1 = gs.get_dropoff_approach_target(1, (1, 6), drop_off, delivering)
        _, wait_2 = gs.get_dropoff_approach_target(2, (1, 6), drop_off, delivering)
        assert wait_0 is False
        assert wait_1 is False
        assert wait_2 is True


class TestIsDropoffCongested:
    def test_not_congested_with_few_bots(self):
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        # One bot near dropoff -- should not be congested
        assert gs.is_dropoff_congested(drop_off, [(1, 7)]) is False

    def test_congested_with_many_bots(self):
        from grocery_bot.game_state import MAX_APPROACH_SLOTS

        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        # Place more bots than MAX_APPROACH_SLOTS near dropoff
        near_positions = gs.dropoff_approach_cells[: MAX_APPROACH_SLOTS + 1]
        if len(near_positions) > MAX_APPROACH_SLOTS:
            assert gs.is_dropoff_congested(drop_off, near_positions) is True

    def test_bots_far_away_not_congested(self):
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        far_bots = [(5, 1), (7, 1), (9, 1), (3, 1)]
        assert gs.is_dropoff_congested(drop_off, far_bots) is False

    def test_bot_on_dropoff_counts(self):
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        from grocery_bot.game_state import MAX_APPROACH_SLOTS

        # Place bots on dropoff itself plus approach cells
        positions = [drop_off, *gs.dropoff_approach_cells[:MAX_APPROACH_SLOTS]]
        assert gs.is_dropoff_congested(drop_off, positions) is True


class TestGetAvoidanceTarget:
    def test_already_far_returns_none(self):
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        # Bot far from dropoff
        result = gs.get_avoidance_target((9, 1), drop_off)
        assert result is None

    def test_near_dropoff_returns_position(self):
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        # Bot right next to dropoff
        result = gs.get_avoidance_target((1, 7), drop_off)
        if result is not None:
            from grocery_bot.game_state import DROPOFF_CONGESTION_RADIUS

            d = gs.dist_static(result, drop_off)
            assert d > DROPOFF_CONGESTION_RADIUS

    def test_avoidance_target_is_walkable(self):
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        result = gs.get_avoidance_target((1, 7), drop_off)
        if result is not None:
            assert result not in gs.blocked_static

    def test_on_dropoff_gets_avoidance(self):
        """Bot standing on dropoff cell should get an avoidance target."""
        gs = _make_gs_with_dropoff()
        drop_off = (1, 8)
        # dist_static(drop_off, drop_off) == 0, which is <= CONGESTION_RADIUS
        result = gs.get_avoidance_target(drop_off, drop_off)
        # Should suggest moving away (if idle spots or wait cells exist)
        if gs.idle_spots or gs.dropoff_wait_cells:
            assert result is not None


class TestUpdateRoundPositions:
    def test_stores_positions(self):
        gs = _make_gs_with_dropoff()
        gs.update_round_positions({0: (1, 1), 1: (5, 5)}, (1, 8))
        assert gs._round_bot_positions == {0: (1, 1), 1: (5, 5)}
        assert gs._round_drop_off == (1, 8)

    def test_clears_targets(self):
        gs = _make_gs_with_dropoff()
        gs._round_bot_targets = {0: (1, 8)}
        gs.update_round_positions({0: (1, 1)}, (1, 8))
        assert gs._round_bot_targets == {}


class TestCountBotsNearDropoff:
    def test_no_bots_returns_zero(self):
        gs = _make_gs_with_dropoff()
        gs.update_round_positions({}, (1, 8))
        assert gs.count_bots_near_dropoff() == 0

    def test_counts_bots_in_approach_zone(self):
        gs = _make_gs_with_dropoff()
        # Place a bot on an approach cell
        if gs.dropoff_approach_cells:
            near_cell = gs.dropoff_approach_cells[0]
            gs.update_round_positions({0: near_cell, 1: (9, 1)}, (1, 8))
            assert gs.count_bots_near_dropoff() >= 1

    def test_excludes_specified_bot(self):
        gs = _make_gs_with_dropoff()
        if gs.dropoff_approach_cells:
            near_cell = gs.dropoff_approach_cells[0]
            gs.update_round_positions({0: near_cell}, (1, 8))
            assert gs.count_bots_near_dropoff(exclude_bot=0) == 0
            assert gs.count_bots_near_dropoff(exclude_bot=1) == 1

    def test_no_zones_returns_zero(self):
        gs = make_gs_with_state()  # no dropoff -> no zones
        gs.update_round_positions({0: (1, 7)}, (1, 8))
        assert gs.count_bots_near_dropoff() == 0


class TestCountBotsTargetingDropoff:
    def test_no_targets_returns_zero(self):
        gs = _make_gs_with_dropoff()
        gs.update_round_positions({0: (1, 1)}, (1, 8))
        assert gs.count_bots_targeting_dropoff() == 0

    def test_counts_bots_targeting(self):
        gs = _make_gs_with_dropoff()
        gs.update_round_positions({0: (1, 1), 1: (5, 5)}, (1, 8))
        gs.notify_bot_target(0, (1, 8))
        gs.notify_bot_target(1, (3, 3))
        assert gs.count_bots_targeting_dropoff() == 1

    def test_excludes_specified_bot(self):
        gs = _make_gs_with_dropoff()
        gs.update_round_positions({0: (1, 1), 1: (5, 5)}, (1, 8))
        gs.notify_bot_target(0, (1, 8))
        gs.notify_bot_target(1, (1, 8))
        assert gs.count_bots_targeting_dropoff(exclude_bot=0) == 1
        assert gs.count_bots_targeting_dropoff(exclude_bot=1) == 1
        assert gs.count_bots_targeting_dropoff() == 2

    def test_no_round_dropoff_returns_zero(self):
        gs = _make_gs_with_dropoff()
        # Don't call update_round_positions -> _round_drop_off is None
        gs._round_drop_off = None
        gs.notify_bot_target(0, (1, 8))
        assert gs.count_bots_targeting_dropoff() == 0


class TestNotifyBotTarget:
    def test_records_target(self):
        gs = _make_gs_with_dropoff()
        gs.notify_bot_target(0, (3, 3))
        assert gs._round_bot_targets[0] == (3, 3)

    def test_none_target(self):
        gs = _make_gs_with_dropoff()
        gs.notify_bot_target(0, None)
        assert gs._round_bot_targets[0] is None
