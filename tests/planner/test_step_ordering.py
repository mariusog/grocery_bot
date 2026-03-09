"""Verify the step chain ordering constraints that cause catastrophic regressions."""

from grocery_bot.planner.round_planner import RoundPlanner


class TestStepChainStructure:
    def test_clear_dropoff_before_idle_deliver(self):
        chain = RoundPlanner._STEP_CHAIN
        clear_idx = next(i for i, s in enumerate(chain) if s.__name__ == "_step_clear_dropoff")
        idle_idx = next(i for i, s in enumerate(chain) if s.__name__ == "_step_idle_nonactive_deliver")
        assert clear_idx < idle_idx

    def test_deliver_at_dropoff_early(self):
        chain = RoundPlanner._STEP_CHAIN
        idx = next(i for i, s in enumerate(chain) if s.__name__ == "_step_deliver_at_dropoff")
        assert idx <= 2

    def test_active_pickup_before_deliver_active(self):
        chain = RoundPlanner._STEP_CHAIN
        pickup = next(i for i, s in enumerate(chain) if s.__name__ == "_step_active_pickup")
        deliver = next(i for i, s in enumerate(chain) if s.__name__ == "_step_deliver_active")
        assert pickup < deliver

    def test_endgame_before_active_pickup(self):
        chain = RoundPlanner._STEP_CHAIN
        endgame = next(i for i, s in enumerate(chain) if s.__name__ == "_step_endgame")
        pickup = next(i for i, s in enumerate(chain) if s.__name__ == "_step_active_pickup")
        assert endgame < pickup

    def test_idle_positioning_is_last(self):
        assert RoundPlanner._STEP_CHAIN[-1].__name__ == "_step_idle_positioning"

    def test_chain_has_19_steps(self):
        assert len(RoundPlanner._STEP_CHAIN) == 19

    def test_all_expected_steps_present(self):
        expected = {
            "_step_spawn_dispersal",
            "_step_preview_bot", "_step_deliver_at_dropoff",
            "_step_deliver_completes_order", "_step_rush_deliver",
            "_step_opportunistic_preview", "_step_inventory_full_deliver",
            "_step_zero_cost_delivery", "_step_early_delivery",
            "_step_endgame",
            "_step_active_pickup", "_step_deliver_active",
            "_step_clear_nonactive_inventory", "_step_preview_prepick",
            "_step_speculative_pickup",
            "_step_break_oscillation",
            "_step_clear_dropoff", "_step_idle_nonactive_deliver",
            "_step_idle_positioning",
        }
        actual = {s.__name__ for s in RoundPlanner._STEP_CHAIN}
        assert actual == expected

    def test_speculative_after_preview_prepick(self):
        chain = RoundPlanner._STEP_CHAIN
        prepick = next(i for i, s in enumerate(chain) if s.__name__ == "_step_preview_prepick")
        spec = next(i for i, s in enumerate(chain) if s.__name__ == "_step_speculative_pickup")
        assert prepick < spec

    def test_break_oscillation_before_idle(self):
        chain = RoundPlanner._STEP_CHAIN
        osc = next(i for i, s in enumerate(chain) if s.__name__ == "_step_break_oscillation")
        idle = next(i for i, s in enumerate(chain) if s.__name__ == "_step_idle_positioning")
        assert osc < idle
