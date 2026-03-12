"""Integration performance spec — ensures the bot can respond within the
server's 2-second deadline using recorded replay maps.

The live server rule:
  "Respond within 2 seconds per round"

If any single round exceeds the budget, the server may skip our actions,
causing a desync that destroys the score. This test catches that.
"""

import glob
import time
from functools import cache

import pytest

import bot
from grocery_bot.simulator.replay_simulator import ReplaySimulator

# Budget: 100ms per round gives 20x safety margin on the 2s server deadline.
# Our bot typically runs in 1-3ms, so 100ms catches severe regressions
# without being flaky.
ROUND_BUDGET_MS = 100

# Hard ceiling — if ANY round exceeds this, something is catastrophically wrong.
ROUND_HARD_LIMIT_MS = 1000

# Minimum score thresholds by bot count (sanity check).
MIN_SCORES = {
    1: 100,   # Easy
    3: 80,    # Medium
    5: 50,    # Hard
}


def _latest_maps() -> dict[int, str]:
    """Find the latest replay map for each bot count."""
    maps: dict[int, str] = {}
    for path in sorted(glob.glob("maps/*.json")):
        # Extract bot count from filename like 2026-03-12_22x14_5bot.json
        parts = path.split("_")
        for part in parts:
            if part.endswith("bot.json"):
                num_bots = int(part.replace("bot.json", ""))
                maps[num_bots] = path  # latest date wins (sorted)
    return maps


LATEST_MAPS = _latest_maps()


@cache
def _run_replay_cached(map_path: str) -> tuple:
    """Run a full replay game, measuring per-round decide_actions latency."""
    sim = ReplaySimulator(map_path)
    bot.reset_state()

    round_times: list[float] = []
    while not sim.is_over():
        state = sim.get_state()
        if not state["orders"]:
            break

        t0 = time.perf_counter()
        actions = bot.decide_actions(state)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        round_times.append(elapsed_ms)
        sim.apply_actions(actions)

    result = (sim.score, sim.items_delivered, sim.orders_completed, sim.round)
    max_ms = max(round_times) if round_times else 0
    return result, tuple(round_times), max_ms


def _run_replay(map_path: str) -> tuple[dict, list[float], float]:
    """Run a replay game. Returns (result_dict, round_times_ms, max_ms)."""
    result, round_times, max_ms = _run_replay_cached(map_path)
    score, items_delivered, orders_completed, rounds_used = result
    return (
        {
            "score": score,
            "items_delivered": items_delivered,
            "orders_completed": orders_completed,
            "rounds_used": rounds_used,
        },
        list(round_times),
        max_ms,
    )


# ── Performance: no round exceeds budget ─────────────────────────────────


def _bot_count_params() -> list[tuple[int, str]]:
    """Generate pytest params for available replay maps."""
    return [(n, p) for n, p in sorted(LATEST_MAPS.items())]


class TestRoundLatency:
    """Every round must complete within the response budget."""

    @pytest.mark.parametrize(
        "num_bots,map_path",
        _bot_count_params(),
        ids=[f"{n}bot" for n, _ in _bot_count_params()],
    )
    def test_no_round_exceeds_budget(self, num_bots: int, map_path: str) -> None:
        """No single round should exceed ROUND_BUDGET_MS."""
        if num_bots > 10:
            pytest.skip("Large maps tested separately")
        _, _round_times, max_ms = _run_replay(map_path)
        assert max_ms < ROUND_BUDGET_MS, (
            f"{num_bots}bot: slowest round took {max_ms:.1f}ms "
            f"(budget {ROUND_BUDGET_MS}ms)"
        )

    @pytest.mark.parametrize(
        "num_bots,map_path",
        [(n, p) for n, p in _bot_count_params() if n > 10],
        ids=[f"{n}bot" for n, _ in _bot_count_params() if n > 10],
    )
    @pytest.mark.slow
    def test_large_maps_under_hard_limit(self, num_bots: int, map_path: str) -> None:
        """Large maps must stay under the hard ceiling."""
        _, _round_times, max_ms = _run_replay(map_path)
        assert max_ms < ROUND_HARD_LIMIT_MS, (
            f"{num_bots}bot: slowest round took {max_ms:.1f}ms "
            f"(hard limit {ROUND_HARD_LIMIT_MS}ms)"
        )

    def test_average_latency_under_10ms(self) -> None:
        """Average latency across Easy game should be well under 10ms."""
        if 1 not in LATEST_MAPS:
            pytest.skip("No 1-bot replay map")
        _, round_times, _ = _run_replay(LATEST_MAPS[1])
        avg_ms = sum(round_times) / len(round_times)
        assert avg_ms < 10, f"Average latency {avg_ms:.1f}ms exceeds 10ms"


# ── Score sanity: bot achieves minimum scores ────────────────────────────


class TestScoreSanity:
    """Bot must achieve minimum scores to detect catastrophic regressions."""

    @pytest.mark.parametrize(
        "num_bots,min_score",
        [(n, s) for n, s in MIN_SCORES.items()],
        ids=[f"{n}bot-min{s}" for n, s in MIN_SCORES.items()],
    )
    def test_minimum_score(self, num_bots: int, min_score: int) -> None:
        """Score must exceed minimum threshold."""
        if num_bots not in LATEST_MAPS:
            pytest.skip(f"No {num_bots}-bot replay map")
        result, _, _ = _run_replay(LATEST_MAPS[num_bots])
        assert result["score"] >= min_score, (
            f"{num_bots}bot: score {result['score']} below minimum {min_score}"
        )


# ── Desync resilience: bot recovers from position mismatches ─────────────


class TestDesyncResilience:
    """Simulate desync-like conditions and verify the bot handles them."""

    def test_bot_replans_from_actual_state(self) -> None:
        """When server reports unexpected position, bot should replan."""
        from tests.conftest import make_state

        items = [
            {"id": "i0", "type": "cheese", "position": [4, 2]},
            {"id": "i1", "type": "milk", "position": [6, 2]},
        ]
        orders = [
            {
                "id": "o1",
                "items_required": ["cheese", "milk"],
                "items_delivered": [],
                "complete": False,
                "status": "active",
            },
        ]

        state0 = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=items,
            orders=orders,
        )
        bot.decide_actions(state0)

        # Desync — bot didn't move
        state1 = make_state(
            bots=[{"id": 0, "position": [5, 5], "inventory": []}],
            items=items,
            orders=orders,
            round_num=1,
        )
        actions1 = bot.decide_actions(state1)
        assert actions1[0]["action"] != "wait", (
            "Bot should replan from actual state, not get stuck"
        )

    def test_pickup_failure_from_desync_does_not_blacklist(self) -> None:
        """Pickup failure caused by desync must not blacklist the item."""
        from tests.conftest import make_state

        items = [{"id": "item_0", "type": "cheese", "position": [4, 2]}]
        orders = [
            {
                "id": "o1",
                "items_required": ["cheese"],
                "items_delivered": [],
                "complete": False,
                "status": "active",
            },
        ]

        state0 = make_state(
            bots=[{"id": 0, "position": [4, 3], "inventory": []}],
            items=items,
            orders=orders,
        )
        bot.decide_actions(state0)
        gs = bot._gs

        for r in range(1, 5):
            gs.last_pickup[0] = ("item_0", 0)
            gs.last_expected_pos[0] = (4, 3)
            state = make_state(
                bots=[{"id": 0, "position": [5, 3], "inventory": []}],
                items=items,
                orders=orders,
                round_num=r,
            )
            bot.decide_actions(state)

        assert "item_0" not in gs.blacklisted_items, (
            "Desync pickup failures must not cause blacklisting"
        )
