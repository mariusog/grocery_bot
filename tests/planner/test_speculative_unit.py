"""Unit tests for SpeculativeMixin — speculative item pickup for idle bots."""

from tests.conftest import make_planner
from tests.planner.conftest import _active_order


def _make_large_team(n: int, items: list, orders: list, **kw):
    """Build a large-team planner with n bots spread across valid positions."""
    bots = [{"id": i, "position": [2 + i, 4], "inventory": []} for i in range(n)]
    return make_planner(
        bots=bots,
        items=items,
        orders=orders,
        width=30,
        height=18,
        drop_off=[1, 16],
        **kw,
    )


class TestSpeculativePickup:
    def test_prefers_preview_type_for_speculative_target(self):
        """Preview-order types should outrank unrelated speculative targets."""
        planner = _make_large_team(
            10,
            items=[
                {"id": "active_0", "type": "cheese", "position": [4, 2]},
                {"id": "near_other", "type": "coffee", "position": [18, 4]},
                {"id": "preview_0", "type": "bread", "position": [24, 2]},
            ],
            orders=[
                _active_order(["cheese"]),
                {
                    "id": "preview_1",
                    "items_required": ["bread"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "preview",
                },
            ],
        )
        planner.claimed = set()
        planner.net_preview = {"bread": 1}
        planner._spec_types_claimed = set()
        item, _cell = planner._find_spec_target((18, 4), set(), {})
        assert item is not None
        assert item["type"] == "bread"

    def test_skipped_for_small_teams(self):
        """Speculative pickup only activates for 8+ bots."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [5, 4], "inventory": []},
                {"id": 1, "position": [7, 4], "inventory": []},
            ],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.actions = []
        ctx = planner._build_bot_context(planner.bots[1])
        result = planner._step_speculative_pickup(ctx)
        assert result is False

    def test_skipped_when_has_active(self):
        """Bots carrying active items don't speculate."""
        bots = [{"id": i, "position": [2 + i, 4], "inventory": []} for i in range(8)]
        bots[0]["inventory"] = ["cheese"]
        planner = make_planner(
            bots=bots,
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            width=30,
            height=18,
            drop_off=[1, 16],
        )
        planner.actions = []
        ctx = planner._build_bot_context(planner.bots[0])
        assert ctx.has_active is True
        result = planner._step_speculative_pickup(ctx)
        assert result is False

    def test_skipped_when_inventory_full(self):
        """Bots with full inventory don't speculate."""
        bots = [{"id": i, "position": [2 + i, 4], "inventory": []} for i in range(8)]
        bots[0]["inventory"] = ["a", "b", "c"]
        planner = make_planner(
            bots=bots,
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "a", "position": [6, 2]},
            ],
            orders=[_active_order(["cheese"])],
            width=30,
            height=18,
            drop_off=[1, 16],
        )
        planner.actions = []
        ctx = planner._build_bot_context(planner.bots[0])
        result = planner._step_speculative_pickup(ctx)
        assert result is False

    def test_skipped_when_last_slot_and_active_on_shelves(self):
        """Don't fill last slot with speculative on huge teams (15+)."""
        bots = [{"id": i, "position": [2 + i, 4], "inventory": []} for i in range(20)]
        # Bot 0 has 2 non-active items — 1 slot left
        bots[0]["inventory"] = ["bread", "butter"]
        planner = make_planner(
            bots=bots,
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [3, 4]},  # adjacent to bot 0
            ],
            orders=[_active_order(["cheese"])],
            width=30,
            height=18,
            drop_off=[1, 16],
        )
        planner.actions = []
        ctx = planner._build_bot_context(planner.bots[0])
        # Bot carries no active items, has 1 free slot, active items on shelves
        assert ctx.has_active is False
        assert planner.active_on_shelves > 0
        result = planner._step_speculative_pickup(ctx)
        assert result is False, "Should not fill last slot with speculative"

    def test_last_slot_guard_skipped_for_small_teams(self):
        """Teams < 15 should still speculate even on last slot."""
        bots = [{"id": i, "position": [2 + i, 4], "inventory": []} for i in range(10)]
        bots[0]["inventory"] = ["bread", "butter"]  # 2/3, 1 free
        planner = make_planner(
            bots=bots,
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [3, 4]},  # adjacent to bot 0
            ],
            orders=[_active_order(["cheese"])],
            width=30,
            height=18,
            drop_off=[1, 16],
        )
        planner.actions = []
        planner._speculative_pickers = 0
        planner._spec_types_claimed = set()
        ctx = planner._build_bot_context(planner.bots[0])
        result = planner._step_speculative_pickup(ctx)
        # 10-bot team should NOT be blocked by the 15+ guard
        assert result is True

    def test_speculative_allowed_with_two_free_slots(self):
        """Allow speculative pickup when bot has 2+ free slots on huge teams."""
        bots = [{"id": i, "position": [2 + i, 4], "inventory": []} for i in range(20)]
        bots[0]["inventory"] = ["bread"]  # 1 item, 2 free slots
        planner = make_planner(
            bots=bots,
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [3, 4]},  # adjacent to bot 0
            ],
            orders=[_active_order(["cheese"])],
            width=30,
            height=18,
            drop_off=[1, 16],
        )
        planner.actions = []
        planner._speculative_pickers = 0
        planner._spec_types_claimed = set()
        ctx = planner._build_bot_context(planner.bots[0])
        assert ctx.has_active is False
        assert planner.active_on_shelves > 0
        result = planner._step_speculative_pickup(ctx)
        # Should be allowed — bot still has 2 slots, can pick spec + active later
        assert result is True

    def test_activates_for_idle_bot_on_large_team(self):
        """Idle bot on 10-bot team should speculate when active items covered."""
        bots = [{"id": i, "position": [2 + i, 4], "inventory": []} for i in range(10)]
        items = [
            {"id": "i0", "type": "cheese", "position": [4, 2]},
            {"id": "i1", "type": "milk", "position": [6, 2]},
            {"id": "i2", "type": "bread", "position": [8, 2]},
        ]
        planner = make_planner(
            bots=bots,
            items=items,
            orders=[_active_order(["cheese"])],
            width=30,
            height=18,
            drop_off=[1, 16],
        )
        # After plan(), check that some bots got non-wait actions
        non_wait = [a for a in planner.actions if a["action"] != "wait"]
        assert len(non_wait) > 0

    def test_diversity_avoids_same_type(self):
        """Speculative pickers should prefer diverse item types."""
        bots = [{"id": i, "position": [2 + i, 4], "inventory": []} for i in range(10)]
        # Team already has 2 copies of "milk"
        bots[0]["inventory"] = ["milk"]
        bots[1]["inventory"] = ["milk"]
        items = [
            {"id": "i0", "type": "cheese", "position": [4, 2]},
            {"id": "i1", "type": "milk", "position": [6, 2]},
            {"id": "i2", "type": "bread", "position": [8, 2]},
        ]
        planner = make_planner(
            bots=bots,
            items=items,
            orders=[_active_order(["cheese"])],
            width=30,
            height=18,
            drop_off=[1, 16],
        )
        planner.actions = []
        planner._speculative_pickers = 0
        planner._spec_types_claimed = set()
        # Bot 5 (idle, empty) should NOT pick "milk" (2 copies already)
        ctx = planner._build_bot_context(planner.bots[5])
        if not ctx.has_active and len(ctx.inv) == 0:
            result = planner._try_speculative_pickup(
                ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.inv, ctx.blocked,
            )
            if result:
                # Claimed type should NOT be milk
                assert "milk" not in planner._spec_types_claimed

    def test_respects_max_speculative_limit(self):
        """Should not exceed the per-round speculative picker limit."""
        bots = [{"id": i, "position": [2 + i, 4], "inventory": []} for i in range(10)]
        items = [
            {"id": f"i{j}", "type": f"type_{j}", "position": [4 + j * 2, 2]}
            for j in range(10)
        ]
        planner = make_planner(
            bots=bots,
            items=items,
            orders=[_active_order(["type_0"])],
            width=30,
            height=18,
            drop_off=[1, 16],
        )
        # Set pickers to max limit — should block further speculative pickup
        num_bots = len(planner.bots)
        max_spec = max(num_bots // 2, 4)
        planner._speculative_pickers = max_spec
        planner.actions = []
        ctx = planner._build_bot_context(planner.bots[9])
        result = planner._step_speculative_pickup(ctx)
        assert result is False
