"""Spawn dispersal tests for large teams."""

import bot
from grocery_bot.planner.round_planner import RoundPlanner
from grocery_bot.simulator.replay_simulator import ReplaySimulator


class TestSpawnDispersalTargets:
    def test_20bot_dispersal_targets_computed(self):
        """20-bot map should compute dispersal targets for all bots."""
        sim = ReplaySimulator("maps/2026-03-08_30x18_20bot.json")
        bot.reset_state()
        state = sim.get_state()
        bot.decide_actions(state)
        gs = bot._gs
        targets = gs.spawn_dispersal_targets
        assert targets is not None
        assert len(targets) > 0, "Should have dispersal targets for 20-bot map"

    def test_dispersal_targets_have_unique_y_values(self):
        """Dispersal targets should span multiple Y rows."""
        sim = ReplaySimulator("maps/2026-03-08_30x18_20bot.json")
        bot.reset_state()
        state = sim.get_state()
        bot.decide_actions(state)
        gs = bot._gs
        targets = gs.spawn_dispersal_targets
        ys = {t[1] for t in targets.values()}
        assert len(ys) >= 3, f"Expected 3+ unique Y values, got {sorted(ys)}"

    def test_assigned_bots_skip_dispersal(self):
        """Bots with active assignments should not be dispersed."""
        sim = ReplaySimulator("maps/2026-03-08_30x18_20bot.json")
        bot.reset_state()
        state = sim.get_state()
        bot.decide_actions(state)
        gs = bot._gs

        planner = RoundPlanner(gs, state, full_state=state)
        planner.plan()

        for bid, assignment in planner.bot_assignments.items():
            if assignment:
                b = planner.bots_by_id.get(bid)
                if b is None:
                    continue
                ctx = planner._build_bot_context(b)
                result = planner._step_spawn_dispersal(ctx)
                assert result is False, f"Assigned bot {bid} should not be dispersed"
