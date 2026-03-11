"""Tests for TeamConfig — team-size-dependent configuration profiles."""

from grocery_bot.team_config import get_team_config


class TestSoloBot:
    def test_solo_basics(self):
        cfg = get_team_config(1)
        assert cfg.num_bots == 1
        assert cfg.multi_bot is False
        assert cfg.use_coordination is False
        assert cfg.enable_speculative is False
        assert cfg.enable_spec_assignment is False
        assert cfg.use_predictions is False
        assert cfg.use_temporal_bfs is False
        assert cfg.blocking_radius == float("inf")


class TestSmallTeam:
    def test_3bot(self):
        cfg = get_team_config(3)
        assert cfg.multi_bot is True
        assert cfg.use_coordination is False
        assert cfg.enable_speculative is False
        assert cfg.use_predictions is False
        assert cfg.use_temporal_bfs is True
        assert cfg.blocking_radius == float("inf")
        assert cfg.use_dropoff_weight is False
        assert cfg.preview_stage_weight == 0.0
        assert cfg.use_idle_spots is False


class TestMediumTeam:
    def test_5bot(self):
        cfg = get_team_config(5)
        assert cfg.use_coordination is True
        assert cfg.enable_speculative is True
        assert cfg.enable_spec_assignment is False
        assert cfg.use_predictions is False
        assert cfg.use_dropoff_weight is True
        assert cfg.preview_stage_weight == 0.5
        assert cfg.max_concurrent_deliverers == 2
        assert cfg.max_nonactive_deliverers == 2


class TestLargeTeam:
    def test_10bot(self):
        cfg = get_team_config(10)
        assert cfg.use_coordination is True
        assert cfg.enable_speculative is True
        assert cfg.enable_spec_assignment is True
        assert cfg.use_predictions is True
        assert cfg.use_idle_spots is True
        assert cfg.use_corridor_penalty is True
        assert cfg.preview_stage_weight == 0.4
        assert cfg.target_attraction_weight == 0.0
        assert cfg.max_concurrent_deliverers == max(2, 10 // 4)
        assert cfg.max_nonactive_deliverers == max(1, 10 // 3)
        assert cfg.extra_preview_roles is True


class TestHugeTeam:
    def test_20bot(self):
        cfg = get_team_config(20)
        assert cfg.blocking_radius == 5.0
        assert cfg.max_concurrent_deliverers == max(2, 20 // 4)
        assert cfg.max_nonactive_deliverers == max(1, 20 // 3)

    def test_15bot_blocking_radius(self):
        cfg = get_team_config(15)
        assert cfg.blocking_radius == 5.0


class TestMethods:
    def test_max_walkers_large(self):
        cfg = get_team_config(10)
        assert cfg.max_walkers(3) == max(2, 10 - 3 - 2)

    def test_max_walkers_small(self):
        cfg = get_team_config(5)
        assert cfg.max_walkers(3) == max(2, 5 // 2)

    def test_nonactive_clear_min_inv_large_assigned(self):
        cfg = get_team_config(10)
        assert cfg.nonactive_clear_min_inv(has_assignment=True) == 1

    def test_nonactive_clear_min_inv_large_unassigned(self):
        cfg = get_team_config(10)
        assert cfg.nonactive_clear_min_inv(has_assignment=False) == 2

    def test_nonactive_clear_min_inv_small(self):
        cfg = get_team_config(3)
        assert cfg.nonactive_clear_min_inv(has_assignment=False) == 2

    def test_nonactive_clear_min_inv_medium(self):
        cfg = get_team_config(5)
        assert cfg.nonactive_clear_min_inv(has_assignment=False) == 3

    def test_preview_prepick_force_large_idle(self):
        cfg = get_team_config(10)
        assert cfg.preview_prepick_force(False, False, 2) is True

    def test_preview_prepick_force_large_assigned(self):
        cfg = get_team_config(10)
        assert cfg.preview_prepick_force(True, False, 0) is False

    def test_preview_prepick_force_medium(self):
        cfg = get_team_config(6)
        assert cfg.preview_prepick_force(False, False, 0) is True
        assert cfg.preview_prepick_force(False, False, 1) is False

    def test_preview_prepick_force_small(self):
        cfg = get_team_config(3)
        assert cfg.preview_prepick_force(False, False, 0) is True
        assert cfg.preview_prepick_force(False, False, 1) is True
        assert cfg.preview_prepick_force(False, False, 2) is False

    def test_rush_max_deliverers(self):
        cfg = get_team_config(10)
        assert cfg.rush_max_deliverers() == max(2, 10 // 4)

    def test_max_spec_pickers(self):
        cfg = get_team_config(10)
        assert cfg.max_spec_pickers() == max(10 // 2, 4)

    def test_num_zones(self):
        cfg8 = get_team_config(8)
        assert cfg8.num_zones(6) == max(2, 6 // 3)
        cfg5 = get_team_config(5)
        assert cfg5.num_zones(4) == max(1, 4 // 2)
        cfg3 = get_team_config(3)
        assert cfg3.num_zones(3) == 1


class TestBoundaries:
    """Verify correct config at every team-size boundary."""

    def test_4bot_enables_coordination(self):
        assert get_team_config(3).use_coordination is False
        assert get_team_config(4).use_coordination is True

    def test_5bot_enables_speculative(self):
        assert get_team_config(4).enable_speculative is False
        assert get_team_config(5).enable_speculative is True

    def test_8bot_enables_predictions(self):
        assert get_team_config(7).use_predictions is False
        assert get_team_config(8).use_predictions is True

    def test_8bot_enables_spec_assignment(self):
        assert get_team_config(7).enable_spec_assignment is False
        assert get_team_config(8).enable_spec_assignment is True

    def test_blocking_radius_transitions(self):
        assert get_team_config(4).blocking_radius == float("inf")
        assert get_team_config(5).blocking_radius == 4.0
        assert get_team_config(8).blocking_radius == 5.0
        assert get_team_config(14).blocking_radius == 5.0
        assert get_team_config(15).blocking_radius == 5.0
