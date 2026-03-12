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

    def test_dispersal_targets_have_spatial_spread(self):
        """Dispersal targets should span multiple positions (X or Y)."""
        sim = ReplaySimulator("maps/2026-03-08_30x18_20bot.json")
        bot.reset_state()
        state = sim.get_state()
        bot.decide_actions(state)
        gs = bot._gs
        targets = gs.spawn_dispersal_targets
        xs = {t[0] for t in targets.values()}
        ys = {t[1] for t in targets.values()}
        spread = max(len(xs), len(ys))
        assert spread >= 3, f"Expected 3+ spread, X={sorted(xs)}, Y={sorted(ys)}"

    def test_dispersal_overrides_assignments_at_spawn(self):
        """Lane dispersal overrides assignments during opening rounds.

        All bots start stacked at spawn — following assignments would
        convoy them single-file, so dispersal takes priority on
        single-dropoff maps (Expert).
        """
        sim = ReplaySimulator("maps/2026-03-12_28x18_10bot.json")
        bot.reset_state()
        state = sim.get_state()
        bot.decide_actions(state)
        gs = bot._gs

        planner = RoundPlanner(gs, state, full_state=state)
        planner.plan()

        dispersed = 0
        for bid in range(len(planner.bots)):
            b = planner.bots_by_id.get(bid)
            if b is None:
                continue
            ctx = planner._build_bot_context(b)
            if planner._step_spawn_dispersal(ctx):
                dispersed += 1
        assert dispersed > 0, "At least some bots should disperse at spawn"
