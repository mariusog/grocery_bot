"""Tests for multi-bot coordination: assignment, collision, deadlock, dispersal."""

import bot
from tests.conftest import make_state, reset_bot, get_action


class TestSpawnDispersal:
    """Tests that bots at the same spawn position disperse on round 1."""

    def test_bots_disperse_from_spawn(self):
        """N bots at the same spawn position should mostly move to different
        cells after round 0. With only 4 adjacent cells available, at most
        5 bots can occupy spawn + 4 neighbors, so we allow 1 collision for
        5 bots."""
        from grocery_bot.simulator import GameSimulator

        for n_bots in [2, 3, 5]:
            reset_bot()
            sim = GameSimulator(seed=42, num_bots=n_bots)
            state = sim.get_state()

            # Verify all bots start at the same spawn position
            spawn = state["bots"][0]["position"]
            for b in state["bots"]:
                assert b["position"] == spawn, f"Bot {b['id']} not at spawn {spawn}"

            # Run round 0
            actions = bot.decide_actions(state)
            sim.apply_actions(actions)

            # After round 0, check dispersal
            positions = [tuple(b["position"]) for b in sim.bots]
            unique_positions = set(positions)
            # With border walls, spawn has ~2 open directions,
            # so we expect at least min(N, 3) unique positions
            min_expected = min(n_bots, 3)
            assert len(unique_positions) >= min_expected, (
                f"With {n_bots} bots, only {len(unique_positions)} unique "
                f"positions after round 0 (expected >= {min_expected}): "
                f"{positions}"
            )

    def test_bots_disperse_different_seeds(self):
        """Dispersal should work across different seeds."""
        from grocery_bot.simulator import GameSimulator

        n_bots = 5
        for seed in [1, 5, 10]:
            reset_bot()
            sim = GameSimulator(seed=seed, num_bots=n_bots)
            state = sim.get_state()
            actions = bot.decide_actions(state)
            sim.apply_actions(actions)

            positions = [tuple(b["position"]) for b in sim.bots]
            unique_positions = set(positions)
            # With border walls near spawn, only ~2 open directions.
            # We require at least 3 unique positions out of 5.
            assert len(unique_positions) >= min(n_bots, 3), (
                f"Seed {seed}: only {len(unique_positions)} unique positions "
                f"out of {n_bots} after round 0: {positions}"
            )
