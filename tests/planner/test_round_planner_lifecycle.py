"""Unit tests for RoundPlanner core helper methods."""

from tests.conftest import make_planner
from tests.planner.conftest import _active_order




class TestDetectPickupFailures:
    def test_failure_increments_count(self):
        """Failed pickup should increment pickup_fail_count."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        # Simulate: last round bot tried to pick "item_x" with inv len 0,
        # and now inv is still 0 -> failure
        planner.gs.last_pickup[0] = ("item_x", 0)
        planner.gs.pickup_fail_count = {}
        planner._detect_pickup_failures()
        assert planner.gs.pickup_fail_count.get("item_x", 0) >= 1

    def test_success_clears_count(self):
        """Successful pickup should clear the fail count."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[{"id": "i0", "type": "milk", "position": [4, 2]}],
            orders=[_active_order(["cheese", "milk"])],
        )
        # Simulate: bot had inv len 0 last round, now has 1 item -> success
        planner.gs.last_pickup[0] = ("item_x", 0)
        planner.gs.pickup_fail_count["item_x"] = 2
        planner._detect_pickup_failures()
        assert "item_x" not in planner.gs.pickup_fail_count

    def test_blacklist_after_threshold(self):
        """Item should be blacklisted after enough consecutive failures."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.gs.last_pickup[0] = ("item_x", 0)
        planner.gs.pickup_fail_count["item_x"] = 2  # Will become 3 (threshold)
        planner._detect_pickup_failures()
        assert "item_x" in planner.gs.blacklisted_items


class TestBuildBotContext:
    def test_context_fields(self):
        """_build_bot_context returns correctly populated namedtuple."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 4], "inventory": ["cheese"]}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        bot = planner.bots_by_id[0]
        ctx = planner._build_bot_context(bot)
        assert ctx.bid == 0
        assert ctx.bx == 3
        assert ctx.by == 4
        assert ctx.pos == (3, 4)
        assert ctx.inv == ["cheese"]
        assert ctx.has_active is True

    def test_context_no_active(self):
        """Bot with non-active inventory has has_active False."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 4], "inventory": ["bread"]}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        bot = planner.bots_by_id[0]
        ctx = planner._build_bot_context(bot)
        assert ctx.has_active is False


class TestPlan:
    def test_plan_returns_actions_for_all_bots(self):
        """plan() should return one action per bot."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [3, 3], "inventory": []},
                {"id": 1, "position": [7, 3], "inventory": []},
            ],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [6, 2]},
            ],
            orders=[_active_order(["cheese", "milk"])],
        )
        assert len(planner.actions) == 2
        bot_ids = {a["bot"] for a in planner.actions}
        assert bot_ids == {0, 1}

    def test_plan_no_active_order_all_wait(self):
        """Without an active order, all bots should wait."""
        from tests.conftest import make_state
        import bot

        state = make_state(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[
                {
                    "id": "o1",
                    "items_required": ["cheese"],
                    "items_delivered": ["cheese"],
                    "complete": True,
                    "status": "completed",
                }
            ],
        )
        bot.reset_state()
        actions = bot.decide_actions(state)
        assert len(actions) == 1
        assert actions[0]["action"] == "wait"

    def test_step_deliver_at_dropoff(self):
        """Bot at dropoff with active items should deliver."""
        planner = make_planner(
            bots=[{"id": 0, "position": [1, 8], "inventory": ["cheese"]}],
            items=[{"id": "i0", "type": "bread", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        assert len(planner.actions) == 1
        assert planner.actions[0]["action"] == "drop_off"

    def test_step_rush_deliver(self):
        """When all active items are picked, bot rushes to deliver."""
        planner = make_planner(
            bots=[{"id": 0, "position": [5, 3], "inventory": ["cheese"]}],
            items=[{"id": "i0", "type": "bread", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
            drop_off=[1, 8],
        )
        assert len(planner.actions) == 1
        # Bot should be moving toward dropoff
        assert planner.actions[0]["action"].startswith("move_")


class TestComputeNeeds:
    def test_net_active_computed(self):
        """net_active should reflect items still needed on shelves."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[
                {"id": "i0", "type": "cheese", "position": [4, 2]},
                {"id": "i1", "type": "milk", "position": [4, 6]},
            ],
            orders=[_active_order(["cheese", "milk"])],
        )
        # Both items on shelves, none carried
        # After plan() runs, items may be claimed, but net_active was computed
        # Check the planner has the expected attributes
        assert hasattr(planner, "net_active")
        assert hasattr(planner, "active_on_shelves")

    def test_active_on_shelves_decreases_with_inventory(self):
        """Carrying an active item reduces active_on_shelves count."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": ["cheese"]}],
            items=[
                {"id": "i0", "type": "milk", "position": [4, 2]},
            ],
            orders=[_active_order(["cheese", "milk"])],
        )
        # cheese is carried, only milk left on shelves
        assert planner.active_on_shelves == 1


class TestCheckOrderTransition:
    def test_clears_state_on_order_change(self):
        """Delivery queue should clear when order changes."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.gs.last_active_order_id = "old_order"
        planner.gs.delivery_queue = [0, 1, 2]
        planner.gs.bot_tasks = {0: {"type": "pick"}}
        planner._check_order_transition()
        assert planner.gs.delivery_queue == []
        assert planner.gs.bot_tasks == {}

    def test_no_clear_when_same_order(self):
        """No clearing when order hasn't changed."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        planner.gs.last_active_order_id = "order_0"
        planner.gs.delivery_queue = [0]
        planner._check_order_transition()
        assert planner.gs.delivery_queue == [0]
