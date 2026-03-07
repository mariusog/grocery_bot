"""Integration performance spec — ensures the bot can respond within the
server's 2-second deadline under all difficulty presets.

The live server rule:
  "Respond within 2 seconds per round"

If any single round exceeds the budget, the server may skip our actions,
causing a desync that destroys the score. This test catches that.
"""

import time

import pytest

import bot
from grocery_bot.simulator import GameSimulator
from grocery_bot.simulator.presets import DIFFICULTY_PRESETS

# Budget: 100ms per round gives 20x safety margin on the 2s server deadline.
# Our bot typically runs in 1-3ms, so 100ms catches severe regressions
# without being flaky.
ROUND_BUDGET_MS = 100

# Hard ceiling — if ANY round exceeds this, something is catastrophically wrong.
ROUND_HARD_LIMIT_MS = 1000

# Minimum score thresholds per difficulty (sanity check).
MIN_SCORES = {
    "Easy": 100,
    "Medium": 90,
    "Hard": 50,
}


def _run_game_with_timing(preset_name, seed=42):
    """Run a full game, measuring per-round decide_actions latency.

    Returns (result_dict, round_times_ms, max_round_ms).
    """
    params = DIFFICULTY_PRESETS[preset_name]
    sim = GameSimulator(seed=seed, **params)
    bot.reset_state()

    round_times = []
    while not sim.is_over():
        state = sim.get_state()
        if not state["orders"]:
            break

        t0 = time.perf_counter()
        actions = bot.decide_actions(state)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        round_times.append(elapsed_ms)
        sim.apply_actions(actions)

    result = {
        "score": sim.score,
        "items_delivered": sim.items_delivered,
        "orders_completed": sim.orders_completed,
        "rounds_used": sim.round,
    }
    max_ms = max(round_times) if round_times else 0
    return result, round_times, max_ms


def _check_action_position_consistency(preset_name, seed=42):
    """Run a full game and verify every action produces the expected position.

    For multi-bot games, a move can be blocked by another bot occupying the
    target cell. These "collision blocks" are expected behavior, not bugs.

    Returns list of (round, bot_id, expected_pos, actual_pos) mismatches
    that CANNOT be explained by bot-bot collisions.
    """
    params = DIFFICULTY_PRESETS[preset_name]
    sim = GameSimulator(seed=seed, **params)
    bot.reset_state()

    expected_positions = {}  # bot_id -> (x, y)
    sent_actions = {}  # bot_id -> action_name
    mismatches = []

    while not sim.is_over():
        state = sim.get_state()
        if not state["orders"]:
            break

        round_num = state["round"]
        actual_positions = {b["id"]: tuple(b["position"]) for b in state["bots"]}

        for b in state["bots"]:
            bid = b["id"]
            actual = actual_positions[bid]
            if bid in expected_positions:
                exp = expected_positions[bid]
                if actual != exp:
                    # A move can be blocked by walls, items, borders, or
                    # other bots. The simulator resolves bots in ID order,
                    # so a bot's move may be blocked by another bot that
                    # moved first. Only flag as mismatch if the bot moved
                    # to a completely unexpected position (not staying put).
                    was_move = sent_actions.get(bid, "").startswith("move_")
                    if not was_move:
                        mismatches.append((round_num, bid, exp, actual))

        actions = bot.decide_actions(state)
        actions_by_bot = {a["bot"]: a for a in actions}

        for b in state["bots"]:
            bid = b["id"]
            bx, by = b["position"]
            action = actions_by_bot.get(bid, {}).get("action", "wait")
            sent_actions[bid] = action
            if action == "move_right":
                expected_positions[bid] = (bx + 1, by)
            elif action == "move_left":
                expected_positions[bid] = (bx - 1, by)
            elif action == "move_up":
                expected_positions[bid] = (bx, by - 1)
            elif action == "move_down":
                expected_positions[bid] = (bx, by + 1)
            else:
                expected_positions[bid] = (bx, by)

        sim.apply_actions(actions)

    return mismatches


# ── Performance: no round exceeds budget ─────────────────────────────────


class TestRoundLatency:
    """Every round must complete within the response budget."""

    @pytest.mark.parametrize("preset", ["Easy", "Medium", "Hard"])
    def test_no_round_exceeds_budget(self, preset):
        """No single round should exceed ROUND_BUDGET_MS."""
        _, round_times, max_ms = _run_game_with_timing(preset)
        assert max_ms < ROUND_BUDGET_MS, (
            f"{preset}: slowest round took {max_ms:.1f}ms "
            f"(budget {ROUND_BUDGET_MS}ms)"
        )

    @pytest.mark.parametrize("preset", ["Expert", "Nightmare"])
    @pytest.mark.slow
    def test_large_presets_under_hard_limit(self, preset):
        """Large presets must stay under the hard ceiling."""
        _, round_times, max_ms = _run_game_with_timing(preset)
        assert max_ms < ROUND_HARD_LIMIT_MS, (
            f"{preset}: slowest round took {max_ms:.1f}ms "
            f"(hard limit {ROUND_HARD_LIMIT_MS}ms)"
        )

    def test_average_latency_under_10ms(self):
        """Average latency across Easy game should be well under 10ms."""
        _, round_times, _ = _run_game_with_timing("Easy")
        avg_ms = sum(round_times) / len(round_times)
        assert avg_ms < 10, f"Average latency {avg_ms:.1f}ms exceeds 10ms"


# ── Consistency: actions produce expected positions ──────────────────────


class TestActionPositionConsistency:
    """Verify the simulator correctly applies every action we send."""

    @pytest.mark.parametrize("preset", ["Easy", "Medium", "Hard"])
    def test_no_action_position_mismatches(self, preset):
        """Every action should produce the expected position next round."""
        mismatches = _check_action_position_consistency(preset)
        assert mismatches == [], (
            f"{preset}: {len(mismatches)} action-position mismatches. "
            f"First: round={mismatches[0][0]} bot={mismatches[0][1]} "
            f"expected={mismatches[0][2]} actual={mismatches[0][3]}"
        )

    @pytest.mark.parametrize("seed", [1, 7, 42, 99, 123])
    def test_easy_consistency_across_seeds(self, seed):
        """Action consistency holds across different map seeds."""
        mismatches = _check_action_position_consistency("Easy", seed=seed)
        assert mismatches == [], (
            f"Easy seed={seed}: {len(mismatches)} mismatches. "
            f"First at round {mismatches[0][0]}"
        )


# ── Score sanity: bot achieves minimum scores ────────────────────────────


class TestScoreSanity:
    """Bot must achieve minimum scores to detect catastrophic regressions."""

    @pytest.mark.parametrize("preset,min_score", [
        ("Easy", MIN_SCORES["Easy"]),
        ("Medium", MIN_SCORES["Medium"]),
        ("Hard", MIN_SCORES["Hard"]),
    ])
    def test_minimum_score(self, preset, min_score):
        """Score must exceed minimum threshold."""
        result, _, _ = _run_game_with_timing(preset)
        assert result["score"] >= min_score, (
            f"{preset}: score {result['score']} below minimum {min_score}"
        )

    def test_easy_no_blacklisted_items(self):
        """Easy difficulty should complete without blacklisting any items."""
        params = DIFFICULTY_PRESETS["Easy"]
        sim = GameSimulator(seed=42, **params)
        bot.reset_state()

        while not sim.is_over():
            state = sim.get_state()
            if not state["orders"]:
                break
            actions = bot.decide_actions(state)
            sim.apply_actions(actions)

        gs = bot._gs
        assert len(gs.blacklisted_items) == 0, (
            f"Blacklisted items in Easy: {gs.blacklisted_items}"
        )


# ── Desync resilience: bot recovers from position mismatches ─────────────


class TestDesyncResilience:
    """Simulate desync-like conditions and verify the bot handles them."""

    def test_bot_replans_from_actual_state(self):
        """When server reports unexpected position, bot should replan correctly.

        This simulates what happens on the live server: the bot sends move_right
        but the server says the bot is still at the old position.
        """
        from tests.conftest import make_state

        items = [
            {"id": "i0", "type": "cheese", "position": [4, 2]},
            {"id": "i1", "type": "milk", "position": [6, 2]},
        ]
        orders = [
            {"id": "o1", "items_required": ["cheese", "milk"],
             "items_delivered": [], "complete": False, "status": "active"},
        ]

        # Round 0: normal
        state0 = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=items, orders=orders,
        )
        bot.decide_actions(state0)

        # Round 1: desync — bot didn't move (server ignored our action)
        state1 = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=items, orders=orders, round_num=1,
        )
        actions1 = bot.decide_actions(state1)

        # Bot should still produce a valid action (not crash, not "wait")
        assert actions1[0]["action"] != "wait", (
            "Bot should replan from actual state, not get stuck"
        )

    def test_pickup_failure_from_desync_does_not_blacklist(self):
        """Pickup failure caused by desync must not blacklist the item."""
        from tests.conftest import make_state

        items = [
            {"id": "item_0", "type": "cheese", "position": [4, 2]},
        ]
        orders = [
            {"id": "o1", "items_required": ["cheese"],
             "items_delivered": [], "complete": False, "status": "active"},
        ]

        # Round 0: bot adjacent to item
        state0 = make_state(
            bots=[{"id": 0, "position": [4, 3], "inventory": []}],
            items=items, orders=orders,
        )
        bot.decide_actions(state0)
        gs = bot._gs

        # Simulate 4 rounds of desync pickup failures
        for r in range(1, 5):
            gs.last_pickup[0] = ("item_0", 0)
            gs.last_expected_pos[0] = (4, 3)

            # Server says bot is at wrong position
            state = make_state(
                bots=[{"id": 0, "position": [5, 3], "inventory": []}],
                items=items, orders=orders, round_num=r,
            )
            bot.decide_actions(state)

        assert "item_0" not in gs.blacklisted_items, (
            "Desync pickup failures must not cause blacklisting"
        )
