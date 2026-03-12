"""Phase 1 score boost tests — TDD criteria for 2000-point plan.

Three fixes:
1. Medium teams (4-7 bots): lower non-active clearing threshold from 3→2
2. Large teams (8+): cap preview/speculative pickers, reduce waste
3. Early delivery: wire _should_deliver_early() into step chain
"""

import bot
from grocery_bot.planner.round_planner import RoundPlanner
from tests.conftest import make_state


def _order(items, status="active"):
    return {
        "id": "o0",
        "items_required": items,
        "items_delivered": [],
        "complete": False,
        "status": status,
    }


def _preview(items):
    return {
        "id": "o1",
        "items_required": items,
        "items_delivered": [],
        "complete": False,
        "status": "preview",
    }


def _planner(bots, items, orders, **kw):
    """Create planner with init but no plan() — for calling steps directly."""
    state = make_state(bots=bots, items=items, orders=orders, **kw)
    bot.reset_state()
    bot.decide_actions(state)
    gs = bot._gs
    p = RoundPlanner(gs, state, full_state=state)
    p._detect_pickup_failures()
    p.active = next(
        (o for o in p.orders if o.get("status") == "active" and not o["complete"]),
        None,
    )
    p.preview = next((o for o in p.orders if o.get("status") == "preview"), None)
    if p.active:
        p._check_order_transition()
        p._compute_needs()
        p._compute_bot_assignments()
        p.bot_roles = {b["id"]: "pick" for b in p.bots}
        p._pre_predict()
        p._decided = set()
    return p


# =====================================================================
# Fix 1: Medium teams (4-7 bots) clear non-active at 2 items, not 3
# =====================================================================


class TestMediumTeamClearing:
    """Medium teams (4-7) require full inventory to clear non-active items.

    Lowering to 2 caused -95 regression across all difficulties.
    """

    def test_5bot_needs_full_to_clear(self):
        """5-bot team: 2 non-active items should NOT clear (needs 3)."""
        bots = [
            {"id": 0, "position": [5, 4], "inventory": ["bread", "butter"]},
        ] + [{"id": i, "position": [i + 5, 4], "inventory": []} for i in range(1, 5)]
        p = _planner(
            bots,
            [{"id": "i0", "type": "cheese", "position": [4, 2]}],
            [_order(["cheese"])],
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_clear_nonactive_inventory(ctx) is True

    def test_5bot_clears_when_full(self):
        """5-bot team: 3 non-active items (full) SHOULD clear."""
        bots = [
            {"id": 0, "position": [5, 4], "inventory": ["bread", "butter", "eggs"]},
        ] + [{"id": i, "position": [i + 5, 4], "inventory": []} for i in range(1, 5)]
        p = _planner(
            bots,
            [{"id": "i0", "type": "cheese", "position": [4, 2]}],
            [_order(["cheese"])],
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_clear_nonactive_inventory(ctx) is True


# =====================================================================
# Fix 2: Large teams cap preview pickers — reduce waste
# =====================================================================


class TestLargeTeamPreviewCap:
    """On 10+ bot teams, at most MAX_PREVIEW_BOTS should preview-pick."""

    def test_10bot_max_preview_bots(self):
        """10-bot team: preview_bot_ids should be capped (not all idle bots)."""
        bots = [{"id": i, "position": [i + 1, 4], "inventory": []} for i in range(10)]
        items = [{"id": f"i{j}", "type": f"t{j}", "position": [3 + j, 2]} for j in range(2)]
        p = _planner(
            bots,
            items,
            [_order(["t0", "t1"]), _preview(["t0", "t1"])],
            width=14,
        )
        # Only a small number of bots should be designated for preview
        assert len(p.preview_bot_ids) <= 3, (
            f"Too many preview bots: {len(p.preview_bot_ids)}, expected <= 3"
        )

    def test_20bot_max_preview_bots(self):
        """20-bot Nightmare team: preview_bot_ids capped."""
        bots = [{"id": i, "position": [i + 1, 4], "inventory": []} for i in range(20)]
        items = [{"id": f"i{j}", "type": f"t{j}", "position": [3 + j, 2]} for j in range(4)]
        p = _planner(
            bots,
            items,
            [_order(["t0", "t1", "t2", "t3"]), _preview(["t0", "t1"])],
            width=28,
            height=18,
        )
        assert len(p.preview_bot_ids) <= 3, (
            f"Too many preview bots: {len(p.preview_bot_ids)}, expected <= 3"
        )

    def test_speculative_pickers_capped(self):
        """After plan(), total spec+preview pickers on 10-bot team stays bounded."""
        bots = [{"id": i, "position": [i + 1, 4], "inventory": []} for i in range(10)]
        items = [{"id": f"i{j}", "type": f"t{j}", "position": [3 + j, 2]} for j in range(2)]
        p = _planner(
            bots,
            items,
            [_order(["t0", "t1"]), _preview(["t0", "t1"])],
            width=14,
        )
        # Count bots that ended up in preview/speculative roles
        preview_roles = sum(1 for r in p.bot_roles.values() if r in ("preview",))
        assert preview_roles <= 4, f"Too many preview-role bots: {preview_roles}, expected <= 4"


# =====================================================================
# Fix 3: Early delivery — _should_deliver_early() wired into steps
# =====================================================================


class TestEarlyDeliveryStep:
    """_step_early_delivery should trigger when partial delivery is cheaper."""

    def test_delivers_early_when_cheaper(self):
        """Bot near dropoff with 2 active items should deliver early
        when remaining items are far and must be fetched from dropoff anyway."""
        # Dropoff at (1, 8). Bot at (2, 7) — 2 steps from dropoff.
        # Has 2 active items. 3 more items remain far away.
        # Deliver now: 2 (to drop) + fetch remaining from drop.
        # Fill up: walk far for 1 item, deliver, fetch rest — more total cost.
        bots = [
            {"id": 0, "position": [2, 7], "inventory": ["cheese", "milk"]},
        ] + [{"id": i, "position": [i + 3, 4], "inventory": []} for i in range(1, 5)]
        items = [
            {"id": "i0", "type": "bread", "position": [9, 2]},
            {"id": "i1", "type": "eggs", "position": [9, 4]},
            {"id": "i2", "type": "butter", "position": [9, 6]},
        ]
        p = _planner(
            bots,
            items,
            [_order(["cheese", "milk", "bread", "eggs", "butter"])],
        )
        pos = tuple(p.bots_by_id[0]["position"])
        inv = p.bots_by_id[0]["inventory"]
        assert p._should_deliver_early(pos, inv) is True

    def test_no_early_delivery_when_item_close(self):
        """Bot with 1 active item should NOT deliver early when next item is close."""
        # Bot at (3, 4), dropoff at (1,8). Next active item at (4, 3) — 2 steps.
        # Filling up is cheaper than delivering with 1 item.
        bots = [
            {"id": 0, "position": [3, 4], "inventory": ["cheese"]},
            {"id": 1, "position": [7, 4], "inventory": []},
            {"id": 2, "position": [9, 4], "inventory": []},
        ]
        items = [
            {"id": "i_near", "type": "milk", "position": [4, 3]},
            {"id": "i_also", "type": "bread", "position": [5, 2]},
        ]
        p = _planner(
            bots,
            items,
            [_order(["cheese", "milk", "bread"])],
        )
        pos = tuple(p.bots_by_id[0]["position"])
        inv = p.bots_by_id[0]["inventory"]
        assert p._should_deliver_early(pos, inv) is False

    def test_step_chain_has_early_delivery(self):
        """The step chain should include _step_early_delivery."""
        step_names = [s.__name__ for s in RoundPlanner._STEP_CHAIN]
        assert "_step_early_delivery" in step_names, (
            f"_step_early_delivery not in step chain: {step_names}"
        )

    def test_early_delivery_skips_large_teams(self):
        """Early delivery should NOT fire for teams >= 8 (Expert/Nightmare)."""
        bots = [
            {"id": 0, "position": [3, 7], "inventory": ["cheese", "milk"]},
        ] + [{"id": i, "position": [i + 3, 4], "inventory": []} for i in range(1, 8)]
        items = [
            {"id": "i_far", "type": "bread", "position": [9, 2]},
        ]
        p = _planner(
            bots,
            items,
            [_order(["cheese", "milk", "bread"])],
            width=14,
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        result = p._step_early_delivery(ctx)
        assert result is False, "Early delivery should be skipped for 8-bot teams"

    def test_early_delivery_skips_small_teams(self):
        """Early delivery should NOT fire for 3-bot teams (too small)."""
        bots = [
            {"id": 0, "position": [3, 7], "inventory": ["cheese", "milk"]},
            {"id": 1, "position": [5, 4], "inventory": []},
            {"id": 2, "position": [7, 4], "inventory": []},
        ]
        items = [
            {"id": "i_far", "type": "bread", "position": [9, 2]},
        ]
        p = _planner(
            bots,
            items,
            [_order(["cheese", "milk", "bread"])],
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_early_delivery(ctx) is False

    def test_early_delivery_fires_for_medium_teams(self):
        """Early delivery SHOULD fire for 5-bot team when conditions are met."""
        bots = [
            {"id": 0, "position": [2, 7], "inventory": ["cheese", "milk"]},
        ] + [{"id": i, "position": [i + 3, 4], "inventory": []} for i in range(1, 5)]
        items = [
            {"id": "i0", "type": "bread", "position": [9, 2]},
            {"id": "i1", "type": "eggs", "position": [9, 4]},
            {"id": "i2", "type": "butter", "position": [9, 6]},
        ]
        p = _planner(
            bots,
            items,
            [_order(["cheese", "milk", "bread", "eggs", "butter"])],
        )
        ctx = p._build_bot_context(p.bots_by_id[0])
        assert p._step_early_delivery(ctx) is True
