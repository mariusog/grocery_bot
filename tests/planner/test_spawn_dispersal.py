"""TDD tests for universal spawn dispersal.

When multiple bots start stacked at the same spawn cell, they should
fan out toward DIFFERENT map regions rather than all convoying together.
This must work for ANY team size (2+), not just large teams.

The core problem: all bots BFS toward the same nearest item and form
a snake. The fix: assign each bot a unique dispersal target based on
map geometry so they spread vertically across item rows.
"""

from tests.conftest import make_state
import bot


def _order(items):
    return {
        "id": "o0", "items_required": items, "items_delivered": [],
        "complete": False, "status": "active",
    }


def _spawn_state(num_bots, spawn, items, order_items, **kw):
    """Build a round-0 state with all bots stacked at spawn."""
    bots = [{"id": i, "position": list(spawn), "inventory": []} for i in range(num_bots)]
    return make_state(
        bots=bots,
        items=items,
        orders=[_order(order_items)],
        drop_off=kw.pop("drop_off", [1, 8]),
        round_num=0,
        **kw,
    )


def _run_rounds(state, n_rounds):
    """Run n_rounds and return (final_positions, all_actions_per_round)."""

    bot.reset_state()
    rounds = []
    # Use manual step to avoid needing a full simulator
    for r in range(n_rounds):
        actions = bot.decide_actions(state)
        rounds.append(actions)
        # Update bot positions based on actions (simplified)
        for a in actions:
            b = next(bb for bb in state["bots"] if bb["id"] == a["bot"])
            if a["action"] == "move_up":
                b["position"] = [b["position"][0], b["position"][1] - 1]
            elif a["action"] == "move_down":
                b["position"] = [b["position"][0], b["position"][1] + 1]
            elif a["action"] == "move_left":
                b["position"] = [b["position"][0] - 1, b["position"][1]]
            elif a["action"] == "move_right":
                b["position"] = [b["position"][0] + 1, b["position"][1]]
        state["round"] = r + 1
    positions = {b["id"]: tuple(b["position"]) for b in state["bots"]}
    return positions, rounds


class TestSpawnVerticalSpread:
    """After a few rounds, bots should spread vertically, not convoy."""

    def test_3bot_spread_after_5_rounds(self):
        """3 bots should occupy at least 2 distinct Y coords after 5 rounds."""
        items = [
            {"id": "i0", "type": "cheese", "position": [4, 2]},
            {"id": "i1", "type": "milk", "position": [4, 6]},
            {"id": "i2", "type": "bread", "position": [8, 4]},
        ]
        state = _spawn_state(3, (9, 7), items, ["cheese", "milk", "bread"])
        positions, _ = _run_rounds(state, 5)
        ys = {pos[1] for pos in positions.values()}
        assert len(ys) >= 2, (
            f"Bots stuck on same row after 5 rounds: {positions}"
        )

    def test_5bot_spread_after_5_rounds(self):
        """5 bots should use at least 2 distinct Y coords after 5 rounds."""
        items = [
            {"id": f"i{i}", "type": t, "position": p}
            for i, (t, p) in enumerate([
                ("cheese", [4, 2]), ("milk", [4, 10]),
                ("bread", [8, 2]), ("butter", [8, 10]),
                ("eggs", [6, 6]),
            ])
        ]
        state = _spawn_state(
            5, (9, 7), items, ["cheese", "milk", "bread"],
            width=11, height=13,
        )
        positions, _ = _run_rounds(state, 5)
        ys = {pos[1] for pos in positions.values()}
        assert len(ys) >= 2, (
            f"5 bots stuck on same row after 5 rounds: {positions}"
        )

    def test_10bot_spread_after_8_rounds(self):
        """10 bots should use at least 3 distinct Y coords after 8 rounds."""
        items = [
            {"id": f"i{i}", "type": f"t{i}", "position": [5, 2 + i * 2]}
            for i in range(7)
        ]
        state = _spawn_state(
            10, (26, 16), items, ["t0", "t1"],
            width=28, height=18, drop_off=[1, 16],
        )
        positions, _ = _run_rounds(state, 8)
        ys = {pos[1] for pos in positions.values()}
        assert len(ys) >= 3, (
            f"10 bots lack vertical spread after 8 rounds: {positions}"
        )


class TestSpawnNoConvoy:
    """Bots should not form a single-file convoy heading left."""

    def test_3bot_not_all_same_y_after_3_rounds(self):
        """After 3 rounds, 3 bots should not all be on the same Y row."""
        items = [
            {"id": "i0", "type": "cheese", "position": [4, 2]},
            {"id": "i1", "type": "milk", "position": [4, 6]},
        ]
        state = _spawn_state(3, (9, 7), items, ["cheese", "milk"])
        positions, _ = _run_rounds(state, 3)
        ys = [pos[1] for pos in positions.values()]
        # At least one bot should be on a different row
        assert len(set(ys)) >= 2, (
            f"All 3 bots on same row (convoy): y={ys}"
        )


class TestReplayMapSpread:
    """Test vertical spread on actual replay maps where convoy is observed."""

    def test_5bot_replay_spread_by_round_5(self):
        """5-bot replay: bots should use 2+ Y values by round 5."""
        from grocery_bot.simulator.replay_simulator import ReplaySimulator

        sim = ReplaySimulator("maps/2026-03-08_22x14_5bot.json")
        bot.reset_state()
        for _ in range(5):
            state = sim.get_state()
            actions = bot.decide_actions(state)
            sim.apply_actions(actions)
        final = sim.get_state()
        ys = {tuple(b["position"])[1] for b in final["bots"]}
        assert len(ys) >= 2, (
            f"5-bot replay: all bots on same row by R5: "
            f"{[(b['id'], b['position']) for b in final['bots']]}"
        )

    def test_10bot_replay_spread_by_round_8(self):
        """10-bot replay: bots should use 3+ Y values by round 8."""
        from grocery_bot.simulator.replay_simulator import ReplaySimulator

        sim = ReplaySimulator("maps/2026-03-08_28x18_10bot.json")
        bot.reset_state()
        for _ in range(8):
            state = sim.get_state()
            actions = bot.decide_actions(state)
            sim.apply_actions(actions)
        final = sim.get_state()
        ys = {tuple(b["position"])[1] for b in final["bots"]}
        assert len(ys) >= 3, (
            f"10-bot replay: insufficient vertical spread by R8: "
            f"{[(b['id'], b['position']) for b in final['bots']]}"
        )

    def test_3bot_replay_spread_by_round_4(self):
        """3-bot replay: bots should use 2+ Y values by round 4."""
        from grocery_bot.simulator.replay_simulator import ReplaySimulator

        sim = ReplaySimulator("maps/2026-03-08_16x12_3bot.json")
        bot.reset_state()
        for _ in range(4):
            state = sim.get_state()
            actions = bot.decide_actions(state)
            sim.apply_actions(actions)
        final = sim.get_state()
        ys = {tuple(b["position"])[1] for b in final["bots"]}
        assert len(ys) >= 2, (
            f"3-bot replay: all bots on same row by R4: "
            f"{[(b['id'], b['position']) for b in final['bots']]}"
        )


class TestSpawnRegression:
    """Ensure spawn changes don't break 1-bot or 2-bot games."""

    def test_1bot_unaffected(self):
        """Single bot should move normally, no spawn dispersal."""
        items = [{"id": "i0", "type": "cheese", "position": [4, 2]}]
        state = _spawn_state(1, (9, 7), items, ["cheese"])
        bot.reset_state()
        actions = bot.decide_actions(state)
        assert len(actions) == 1
        assert actions[0]["action"] != "wait", "Single bot should not wait"

    def test_2bot_both_move(self):
        """Two bots should both move on round 0 if exits allow."""
        items = [
            {"id": "i0", "type": "cheese", "position": [4, 2]},
            {"id": "i1", "type": "milk", "position": [4, 6]},
        ]
        state = _spawn_state(2, (5, 4), items, ["cheese", "milk"])
        bot.reset_state()
        actions = bot.decide_actions(state)
        movers = [a for a in actions if a["action"] != "wait"]
        assert len(movers) == 2, (
            f"Both bots should move but got: {[a['action'] for a in actions]}"
        )
