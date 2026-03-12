"""Tests for sequential move resolution in the simulator.

The live server processes moves sequentially by bot ID (0, 1, 2, ...):
- Higher-ID bots can follow lower-ID bots (chain moves)
- Lower-ID bots CANNOT follow higher-ID bots (occupant hasn't moved yet)
- Swap collisions: both blocked (lower blocked first, higher sees lower still there)
- Convergence on empty cell: lower-ID bot wins, higher-ID blocked
"""

from grocery_bot.simulator import GameSimulator


def _make_sim(bots_pos: list[tuple[int, int]], **kw) -> GameSimulator:
    """Create a minimal simulator with bots at specified positions."""
    sim = GameSimulator(seed=42, num_bots=len(bots_pos), **kw)
    sim.walls = []
    sim.shelf_positions = set()
    sim.item_shelves = {}
    sim.items_on_map = []
    for i, (x, y) in enumerate(bots_pos):
        sim.bots[i]["position"] = [x, y]
    return sim


class TestHigherFollowsLower:
    """Higher-ID bot can follow lower-ID bot (lower already moved)."""

    def test_higher_follows_lower(self):
        """Bot 1 moves into cell bot 0 vacated."""
        sim = _make_sim([(3, 4), (4, 4)])
        actions = [
            {"bot": 0, "action": "move_left"},  # -> (2,4)
            {"bot": 1, "action": "move_left"},  # -> (3,4) vacated by bot 0
        ]
        sim.apply_actions(actions)
        assert sim.bots[0]["position"] == [2, 4]
        assert sim.bots[1]["position"] == [3, 4]

    def test_three_bot_chain_higher_follows_lower(self):
        """A->B->C chain works when each bot follows a lower-ID bot."""
        sim = _make_sim([(3, 4), (4, 4), (5, 4)])
        actions = [
            {"bot": 0, "action": "move_left"},  # -> (2,4) free
            {"bot": 1, "action": "move_left"},  # -> (3,4) vacated by bot 0
            {"bot": 2, "action": "move_left"},  # -> (4,4) vacated by bot 1
        ]
        sim.apply_actions(actions)
        assert sim.bots[0]["position"] == [2, 4]
        assert sim.bots[1]["position"] == [3, 4]
        assert sim.bots[2]["position"] == [4, 4]


class TestLowerCannotFollowHigher:
    """Lower-ID bot CANNOT follow higher-ID bot (higher hasn't moved yet)."""

    def test_lower_blocked_by_higher(self):
        """Bot 0 tries to enter bot 1's cell — blocked (bot 1 hasn't moved)."""
        sim = _make_sim([(3, 4), (4, 4)])
        actions = [
            {"bot": 0, "action": "move_right"},  # -> (4,4) bot 1 still there
            {"bot": 1, "action": "move_right"},  # -> (5,4) free
        ]
        sim.apply_actions(actions)
        assert sim.bots[0]["position"] == [3, 4]  # blocked
        assert sim.bots[1]["position"] == [5, 4]  # moved

    def test_three_bot_chain_lower_follows_higher_fails(self):
        """Chain where each bot follows a higher-ID bot: all blocked except last."""
        sim = _make_sim([(3, 4), (4, 4), (5, 4)])
        actions = [
            {"bot": 0, "action": "move_right"},  # -> (4,4) bot 1 still there
            {"bot": 1, "action": "move_right"},  # -> (5,4) bot 2 still there
            {"bot": 2, "action": "move_right"},  # -> (6,4) free
        ]
        sim.apply_actions(actions)
        assert sim.bots[0]["position"] == [3, 4]  # blocked
        assert sim.bots[1]["position"] == [4, 4]  # blocked
        assert sim.bots[2]["position"] == [6, 4]  # moved


class TestConvergenceSequential:
    """Convergence on empty cell: lower-ID bot wins."""

    def test_lower_id_wins_convergence(self):
        """When two bots target same empty cell, lower-ID bot gets it."""
        sim = _make_sim([(3, 4), (5, 4)])
        actions = [
            {"bot": 0, "action": "move_right"},  # -> (4,4) empty, succeeds
            {"bot": 1, "action": "move_left"},  # -> (4,4) bot 0 now there
        ]
        sim.apply_actions(actions)
        assert sim.bots[0]["position"] == [4, 4]  # won
        assert sim.bots[1]["position"] == [5, 4]  # blocked

    def test_three_way_convergence_lower_wins(self):
        """Three bots targeting same empty cell: lowest ID wins."""
        sim = _make_sim([(3, 4), (5, 4), (4, 5)])
        actions = [
            {"bot": 0, "action": "move_right"},  # -> (4,4) empty, succeeds
            {"bot": 1, "action": "move_left"},  # -> (4,4) bot 0 there
            {"bot": 2, "action": "move_up"},  # -> (4,4) bot 0 there
        ]
        sim.apply_actions(actions)
        assert sim.bots[0]["position"] == [4, 4]  # won
        assert sim.bots[1]["position"] == [5, 4]  # blocked
        assert sim.bots[2]["position"] == [4, 5]  # blocked


class TestSwapBlocked:
    """Swap collisions: both blocked under sequential processing."""

    def test_swap_blocks_both(self):
        """A->B while B->A: both blocked.

        Bot 0 tries (4,4) — bot 1 still there — blocked.
        Bot 1 tries (3,4) — bot 0 still there (didn't move) — blocked.
        """
        sim = _make_sim([(3, 4), (4, 4)])
        actions = [
            {"bot": 0, "action": "move_right"},  # -> (4,4)
            {"bot": 1, "action": "move_left"},  # -> (3,4)
        ]
        sim.apply_actions(actions)
        assert sim.bots[0]["position"] == [3, 4]
        assert sim.bots[1]["position"] == [4, 4]


class TestValidMovesUnaffected:
    """Moves into genuinely empty cells must still work."""

    def test_parallel_non_conflicting_moves(self):
        """Two bots moving to different empty cells both succeed."""
        sim = _make_sim([(3, 4), (6, 4)])
        actions = [
            {"bot": 0, "action": "move_right"},  # -> (4,4) free
            {"bot": 1, "action": "move_right"},  # -> (7,4) free
        ]
        sim.apply_actions(actions)
        assert sim.bots[0]["position"] == [4, 4]
        assert sim.bots[1]["position"] == [7, 4]

    def test_opposite_non_conflicting(self):
        """Bots moving apart both succeed."""
        sim = _make_sim([(4, 4), (6, 4)])
        actions = [
            {"bot": 0, "action": "move_left"},  # -> (3,4) free
            {"bot": 1, "action": "move_right"},  # -> (7,4) free
        ]
        sim.apply_actions(actions)
        assert sim.bots[0]["position"] == [3, 4]
        assert sim.bots[1]["position"] == [7, 4]
