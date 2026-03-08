"""Spawn dispersal priority tests for very large teams."""

import bot

from grocery_bot.planner.round_planner import RoundPlanner
from grocery_bot.simulator.replay_simulator import ReplaySimulator


class TestSpawnDispersalPriority:
    def test_spawn_exit_selection_prefers_assigned_waiters(self):
        """Spawn exit selection should prefer assigned bots over preview/idle bots."""
        sim = ReplaySimulator("maps/2026-03-08_30x18_20bot.json")
        bot.reset_state()

        for round_num in range(5):
            state = sim.get_state()
            actions = bot.decide_actions(state)

            planner = RoundPlanner(bot._gs, state, full_state=state)
            planner.plan()

            if round_num == 4:
                spawn = tuple(sim.spawn)
                selected = planner._select_spawn_exit_bots(spawn)
                assert selected, "Expected spawn exit selections on round 4"
                assert all(
                    planner.bot_has_active.get(bid, False)
                    or bool(planner.bot_assignments.get(bid))
                    for bid in selected
                ), f"Unassigned spawn selections on round 4: {selected}"
                preview_ctx = planner._build_bot_context(planner.bots_by_id[2])
                action_count = len(planner.actions)
                assert planner._step_spawn_dispersal(preview_ctx), (
                    "Preview bot should still be held at spawn while assigned "
                    "waiters remain queued"
                )
                assert len(planner.actions) == action_count + 1
                assert planner.actions[-1] == {"bot": 2, "action": "wait"}

            sim.apply_actions(actions)
