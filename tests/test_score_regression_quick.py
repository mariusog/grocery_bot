"""Quick score regression tests using the simulator.

These tests run short (150 round) simulations with multi-bot teams
and assert minimum score/order thresholds. They catch catastrophic
regressions where changes to the step chain, delivery logic, or dropoff
clearing cause orders to stop completing entirely.

Run with: pytest tests/test_score_regression_quick.py -v
"""

import pytest

from grocery_bot import GameState, RoundPlanner
from grocery_bot.simulator import GameSimulator


def _run_sim(num_bots, width, height, num_item_types, max_rounds, seed=42):
    """Run a simulation and return (score, orders_completed, items_delivered)."""
    sim = GameSimulator(
        width=width,
        height=height,
        num_bots=num_bots,
        num_item_types=num_item_types,
        max_rounds=max_rounds,
        seed=seed,
    )
    gs = GameState()
    for _ in range(max_rounds):
        state = sim.get_state()
        if state is None:
            break
        if not gs.blocked_static:
            gs.init_static(state)
        planner = RoundPlanner(gs, state, full_state=state)
        actions = planner.plan()
        sim.apply_actions(actions)
    return sim.score, sim.orders_completed, sim.items_delivered


# ---- Multi-bot regression guards ----
# Thresholds are ~50% of worst-seed baseline to only catch catastrophic drops.
# Current baselines across seeds 42/123/777 (150 rounds):
#   3-bot 16x12: min score=62, min orders=7
#   5-bot 22x14: min score=43, min orders=5
#  10-bot 22x14: min score=34, min orders=4


class TestMultiBotScoreRegression:
    """Catch catastrophic regressions in multi-bot teams."""

    @pytest.mark.parametrize("seed", [42, 123, 777])
    def test_3bot_completes_orders(self, seed):
        score, orders, _ = _run_sim(
            num_bots=3, width=16, height=12,
            num_item_types=8, max_rounds=150, seed=seed,
        )
        assert orders >= 3, (
            f"3-bot (seed={seed}) completed {orders} orders (score={score}). "
            f"Expected >=3."
        )
        assert score >= 25, (
            f"3-bot (seed={seed}) scored {score}. Expected >=25."
        )

    @pytest.mark.parametrize("seed", [42, 123, 777])
    def test_5bot_completes_orders(self, seed):
        score, orders, _ = _run_sim(
            num_bots=5, width=22, height=14,
            num_item_types=10, max_rounds=150, seed=seed,
        )
        assert orders >= 2, (
            f"5-bot (seed={seed}) completed {orders} orders (score={score}). "
            f"Expected >=2."
        )
        assert score >= 20, (
            f"5-bot (seed={seed}) scored {score}. Expected >=20."
        )

    @pytest.mark.parametrize("seed", [42, 123, 777])
    def test_10bot_completes_orders(self, seed):
        score, orders, _ = _run_sim(
            num_bots=10, width=22, height=14,
            num_item_types=10, max_rounds=150, seed=seed,
        )
        assert orders >= 2, (
            f"10-bot (seed={seed}) completed {orders} orders (score={score}). "
            f"Expected >=2."
        )
        assert score >= 15, (
            f"10-bot (seed={seed}) scored {score}. Expected >=15."
        )


class TestSmallTeamScoreRegression:
    """Ensure 1-bot teams maintain basic performance."""

    def test_1bot_completes_orders(self):
        score, orders, _ = _run_sim(
            num_bots=1, width=12, height=10,
            num_item_types=4, max_rounds=150,
        )
        assert orders >= 3, (
            f"1-bot completed {orders} orders (score={score}). Expected >=3."
        )


class TestDropoffNotBlocked:
    """Bots near the dropoff with non-active items must not permanently
    block delivery. Catches step-chain ordering bugs where clear_dropoff
    prevents idle_nonactive_deliver from ever running."""

    def test_bot_with_nonactive_near_dropoff_eventually_delivers(self):
        """A bot with non-active items 1 step from dropoff should move
        toward dropoff within a few rounds."""
        import bot
        from tests.conftest import make_state

        bot.reset_state()
        state = make_state(
            bots=[
                {"id": 0, "position": [2, 8], "inventory": ["eggs", "eggs", "eggs"]},
                {"id": 1, "position": [5, 5], "inventory": []},
                {"id": 2, "position": [7, 5], "inventory": []},
            ],
            items=[
                {"id": "i_milk", "type": "milk", "position": [6, 4]},
                {"id": "i_bread", "type": "bread", "position": [4, 2]},
                {"id": "i_eggs1", "type": "eggs", "position": [8, 4]},
            ],
            orders=[
                {
                    "id": "order_0",
                    "items_required": ["milk", "bread"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                },
                {
                    "id": "order_1",
                    "items_required": ["eggs", "eggs", "eggs"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "preview",
                },
            ],
            drop_off=[1, 8],
            width=11,
            height=9,
        )

        # Run up to 20 rounds, check if bot 0 ever approaches the dropoff
        moved_toward_drop = False
        for _ in range(20):
            actions = bot.decide_actions(state)
            a0 = next(a for a in actions if a["bot"] == 0)
            if a0["action"] in ("move_left", "drop_off"):
                moved_toward_drop = True
                break
            # Simple position tracking for bot 0
            bx, by = state["bots"][0]["position"]
            deltas = {
                "move_left": (-1, 0), "move_right": (1, 0),
                "move_up": (0, -1), "move_down": (0, 1),
            }
            dx, dy = deltas.get(a0["action"], (0, 0))
            state["bots"][0]["position"] = [bx + dx, by + dy]

        assert moved_toward_drop, (
            "Bot 0 with 3 non-active items at d=1 from dropoff never moved "
            "toward dropoff in 20 rounds. Likely blocked by _step_clear_dropoff."
        )
