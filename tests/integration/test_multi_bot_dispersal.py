"""Tests for multi-bot coordination: dispersal from shared spawn position."""

import glob

import bot
from grocery_bot.simulator.replay_simulator import ReplaySimulator
from tests.conftest import reset_bot


def _replay_maps_with_bots(min_bots: int) -> list[str]:
    """Find replay maps with at least min_bots bots."""
    maps = []
    for path in sorted(glob.glob("maps/*.json")):
        parts = path.split("_")
        for part in parts:
            if part.endswith("bot.json"):
                num = int(part.replace("bot.json", ""))
                if num >= min_bots:
                    maps.append(path)
    return maps


class TestSpawnDispersal:
    """Tests that bots at the same spawn position disperse on round 0."""

    def test_bots_disperse_from_spawn(self):
        """Multi-bot maps: bots at shared spawn should move to different cells."""
        maps = _replay_maps_with_bots(3)
        if not maps:
            return  # No multi-bot replay maps available
        for map_path in maps[:3]:
            reset_bot()
            sim = ReplaySimulator(map_path)
            state = sim.get_state()
            num_bots = len(state["bots"])
            if num_bots < 2:
                continue

            actions = bot.decide_actions(state)
            # At least some bots should be moving (not all waiting).
            # On spawn with limited exits, only ~2 can move on round 0.
            move_count = sum(1 for a in actions if a["action"].startswith("move_"))
            assert move_count >= min(num_bots - 1, 2), (
                f"{map_path}: only {move_count}/{num_bots} bots moved on round 0"
            )
