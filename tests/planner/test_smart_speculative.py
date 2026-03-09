"""Test smart speculative assignment using map intelligence.

Instead of blind per-bot search, idle bots get centralized assignments
to preview items, prioritizing items far from dropoff (expensive to
pick later). Each bot gets a unique target — no starvation.
"""

from tests.conftest import make_state
from grocery_bot.planner.round_planner import RoundPlanner
import bot


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
    """Create planner with full init for calling steps directly."""
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
        p._assign_speculative_targets()
        p._pre_predict()
        p._decided = set()
    return p


class TestSpeculativeAssignment:
    """Centralized speculative assignment gives each idle bot a unique target."""

    def test_idle_bots_get_spec_assignments(self):
        """Idle bots on 10-bot team get speculative target assignments."""
        bots = [{"id": i, "position": [2 + i, 8], "inventory": []}
                for i in range(10)]
        items = [
            {"id": "i_bread", "type": "bread", "position": [3, 3]},
            {"id": "i_milk", "type": "milk", "position": [5, 3]},
            {"id": "i_eggs", "type": "eggs", "position": [9, 3]},
        ]
        p = _planner(
            bots, items,
            [_order(["cheese"]), _preview(["bread", "milk", "eggs"])],
            width=14, height=14,
        )
        # Should have some spec assignments
        assert len(p.spec_assignments) > 0, "Idle bots should get spec assignments"

    def test_each_bot_gets_unique_item(self):
        """No two bots target the same item."""
        bots = [{"id": i, "position": [2 + i, 8], "inventory": []}
                for i in range(10)]
        items = [
            {"id": "i_bread", "type": "bread", "position": [3, 3]},
            {"id": "i_milk", "type": "milk", "position": [5, 3]},
            {"id": "i_eggs", "type": "eggs", "position": [9, 3]},
        ]
        p = _planner(
            bots, items,
            [_order(["cheese"]), _preview(["bread", "milk", "eggs"])],
            width=14, height=14,
        )
        assigned_items = [it["id"] for it in p.spec_assignments.values()]
        assert len(assigned_items) == len(set(assigned_items)), (
            "Each bot should target a unique item"
        )

    def test_far_items_assigned_first(self):
        """Items far from dropoff should be prioritized for pre-pickup."""
        # dropoff at (1,12) by default; bread at (11,3) is far, milk at (3,3) is near
        bots = [{"id": i, "position": [2 + i, 8], "inventory": []}
                for i in range(10)]
        items = [
            {"id": "i_near", "type": "milk", "position": [3, 11]},  # near dropoff
            {"id": "i_far", "type": "bread", "position": [11, 3]},  # far from dropoff
        ]
        p = _planner(
            bots, items,
            [_order(["cheese"]), _preview(["bread", "milk"])],
            width=14, height=14,
        )
        # Far item should be assigned (it's more valuable to pre-pick)
        assigned_types = {it["type"] for it in p.spec_assignments.values()}
        assert "bread" in assigned_types, (
            "Far item (bread) should be assigned for pre-pickup"
        )

    def test_bots_with_active_assignment_excluded(self):
        """Bots with active item assignments should not get spec assignments."""
        bots = [{"id": i, "position": [2 + i, 8], "inventory": []}
                for i in range(10)]
        items = [
            {"id": "i_cheese", "type": "cheese", "position": [4, 7]},
            {"id": "i_bread", "type": "bread", "position": [8, 3]},
        ]
        p = _planner(
            bots, items,
            [_order(["cheese"]), _preview(["bread"])],
            width=14, height=14,
        )
        # Bots with active assignments should not be in spec_assignments
        for bid in p.spec_assignments:
            active_assigned = p.bot_assignments.get(bid, [])
            assert not active_assigned, (
                f"Bot {bid} has active assignment but also got spec assignment"
            )

    def test_spec_assigned_bot_walks_to_target(self):
        """Bot with spec assignment should walk toward its target item."""
        bots = [{"id": i, "position": [2 + i, 8], "inventory": []}
                for i in range(10)]
        items = [
            {"id": "i_bread", "type": "bread", "position": [11, 3]},
        ]
        p = _planner(
            bots, items,
            [_order(["cheese"]), _preview(["bread"])],
            width=14, height=14,
        )
        if p.spec_assignments:
            bid = next(iter(p.spec_assignments))
            ctx = p._build_bot_context(p.bots_by_id[bid])
            result = p._step_speculative_pickup(ctx)
            assert result is True, (
                "Bot with spec assignment should act on it"
            )

    def test_no_preview_no_spec_assignments(self):
        """Without a preview order, no speculative assignments are made."""
        bots = [{"id": i, "position": [2 + i, 8], "inventory": []}
                for i in range(10)]
        items = [
            {"id": "i_bread", "type": "bread", "position": [8, 3]},
        ]
        p = _planner(
            bots, items,
            [_order(["cheese"])],  # No preview order
            width=14, height=14,
        )
        assert len(p.spec_assignments) == 0
