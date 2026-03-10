"""Test assigned-bot preview guard extension.

The root cause of poor Hard performance: assigned bots on 5-bot teams
pick up adjacent preview items en route to active items, filling their
inventory with non-active items before reaching active targets.

The fix extends the assigned-bot guard from small teams (<3) to all team
sizes when active items remain on shelves.
"""

import bot
from grocery_bot.planner.round_planner import RoundPlanner
from tests.conftest import make_state


def _order(items, status="active"):
    return {
        "id": "o0", "items_required": items,
        "items_delivered": [], "complete": False, "status": status,
    }


def _preview(items):
    return {
        "id": "o1", "items_required": items,
        "items_delivered": [], "complete": False, "status": "preview",
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


class TestAssignedBotSkipsPreview:
    """Assigned bots should skip opportunistic preview on medium+ teams."""

    def test_5bot_assigned_skips_preview(self):
        """Assigned bot on 5-bot team skips adjacent preview item."""
        bots = [
            {"id": 0, "position": [5, 4], "inventory": []},
        ] + [
            {"id": i, "position": [i + 6, 4], "inventory": []}
            for i in range(1, 5)
        ]
        items = [
            {"id": "i_active", "type": "cheese", "position": [8, 2]},
            {"id": "i_preview", "type": "bread", "position": [5, 3]},
        ]
        p = _planner(
            bots, items,
            [_order(["cheese"]), _preview(["bread"])],
        )
        # Force bot 0 to be assigned to the active item
        p.bot_assignments[0] = [items[0]]
        ctx = p._build_bot_context(p.bots_by_id[0])
        result = p._step_opportunistic_preview(ctx)
        assert result is False, (
            "Assigned bot on 5-bot team should skip preview when active on shelves"
        )

    def test_5bot_unassigned_picks_preview(self):
        """Unassigned bot on 5-bot team can still pick adjacent preview."""
        bots = [
            {"id": 0, "position": [5, 4], "inventory": []},
        ] + [
            {"id": i, "position": [i + 6, 4], "inventory": []}
            for i in range(1, 5)
        ]
        items = [
            {"id": "i_active", "type": "cheese", "position": [8, 2]},
            {"id": "i_preview", "type": "bread", "position": [5, 3]},
        ]
        p = _planner(
            bots, items,
            [_order(["cheese"]), _preview(["bread"])],
        )
        # Ensure bot 0 is NOT assigned
        p.bot_assignments.pop(0, None)
        ctx = p._build_bot_context(p.bots_by_id[0])
        result = p._step_opportunistic_preview(ctx)
        assert result is True, (
            "Unassigned bot should still pick adjacent preview items"
        )

    def test_assigned_picks_preview_when_no_active_on_shelves(self):
        """Assigned bot picks preview when all active items already carried."""
        bots = [
            {"id": 0, "position": [5, 4], "inventory": ["cheese"]},
        ] + [
            {"id": i, "position": [i + 6, 4], "inventory": []}
            for i in range(1, 5)
        ]
        items = [
            {"id": "i_preview", "type": "bread", "position": [5, 3]},
        ]
        p = _planner(
            bots, items,
            [_order(["cheese"]), _preview(["bread"])],
        )
        # Bot 0 carries cheese (active item). No active items on shelves.
        p.bot_assignments[0] = []
        assert p.active_on_shelves == 0
        ctx = p._build_bot_context(p.bots_by_id[0])
        result = p._step_opportunistic_preview(ctx)
        assert result is True, (
            "Assigned bot should pick preview when no active items on shelves"
        )

    def test_10bot_assigned_skips_preview(self):
        """Assigned bot on 10-bot team also skips preview."""
        bots = [
            {"id": 0, "position": [5, 4], "inventory": []},
        ] + [
            {"id": i, "position": [i + 1, 4], "inventory": []}
            for i in range(1, 10)
        ]
        items = [
            {"id": "i_active", "type": "cheese", "position": [8, 2]},
            {"id": "i_preview", "type": "bread", "position": [5, 3]},
        ]
        p = _planner(
            bots, items,
            [_order(["cheese"]), _preview(["bread"])],
            width=14,
        )
        p.bot_assignments[0] = [items[0]]
        ctx = p._build_bot_context(p.bots_by_id[0])
        result = p._step_opportunistic_preview(ctx)
        assert result is False, (
            "Assigned bot on 10-bot team should skip preview"
        )

    def test_2bot_assigned_always_skips(self):
        """2-bot team: assigned bot always skips preview (existing behavior)."""
        bots = [
            {"id": 0, "position": [5, 4], "inventory": []},
            {"id": 1, "position": [7, 4], "inventory": []},
        ]
        items = [
            {"id": "i_active", "type": "cheese", "position": [8, 2]},
            {"id": "i_preview", "type": "bread", "position": [5, 3]},
        ]
        p = _planner(
            bots, items,
            [_order(["cheese"]), _preview(["bread"])],
        )
        p.bot_assignments[0] = [items[0]]
        ctx = p._build_bot_context(p.bots_by_id[0])
        result = p._step_opportunistic_preview(ctx)
        assert result is False, (
            "Assigned bot on 2-bot team should always skip preview"
        )
