"""Test role assignment and delivery queue for multi-bot teams."""

from tests.conftest import make_planner


def _order(items, oid="o0"):
    return {"id": oid, "items_required": items, "items_delivered": [], "complete": False, "status": "active"}


def _preview(items, oid="o1"):
    return {"id": oid, "items_required": items, "items_delivered": [], "complete": False, "status": "preview"}


class TestRoleAssignment:
    def test_3bot_no_coordination(self):
        p = make_planner(
            bots=[{"id": i, "position": [i * 3 + 2, 4], "inventory": []} for i in range(3)],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_order(["cheese"])],
        )
        assert all(r == "pick" for r in p.bot_roles.values())

    def test_4bot_uses_coordination(self):
        p = make_planner(
            bots=[{"id": i, "position": [i * 2 + 2, 4], "inventory": []} for i in range(4)],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]},
                   {"id": "i1", "type": "milk", "position": [6, 2]}],
            orders=[_order(["cheese", "milk"])],
        )
        assert p._use_coordination is True
        assert len(p.bot_roles) == 4

    def test_delivering_bot_gets_deliver_role(self):
        """Bot with full active inventory should get 'deliver' role."""
        bots = [{"id": 0, "position": [2, 4], "inventory": ["cheese", "cheese", "cheese"]}
                ] + [{"id": i, "position": [i + 3, 4], "inventory": []} for i in range(1, 5)]
        p = make_planner(bots=bots,
                         items=[{"id": "i0", "type": "cheese", "position": [8, 2]}],
                         orders=[_order(["cheese", "cheese", "cheese", "cheese"])])
        assert p.bot_roles.get(0) == "deliver"

    def test_preview_bots_when_nearly_complete(self):
        bots = [{"id": 0, "position": [2, 4], "inventory": ["cheese"]}
                ] + [{"id": i, "position": [i + 3, 4], "inventory": []} for i in range(1, 5)]
        p = make_planner(bots=bots,
                         items=[{"id": "i0", "type": "milk", "position": [8, 2]},
                                {"id": "i1", "type": "bread", "position": [6, 2]}],
                         orders=[_order(["cheese", "milk"]), _preview(["bread"])])
        preview_count = sum(1 for r in p.bot_roles.values() if r == "preview")
        assert preview_count >= 1


class TestDeliveryQueue:
    def test_full_active_enters_queue(self):
        """Bot with full active inventory enters delivery queue."""
        bots = [{"id": 0, "position": [5, 4], "inventory": ["cheese", "milk", "bread"]}
                ] + [{"id": i, "position": [i + 2, 6], "inventory": []} for i in range(1, 5)]
        p = make_planner(bots=bots,
                         items=[{"id": "i0", "type": "cheese", "position": [8, 2]}],
                         orders=[_order(["cheese", "milk", "bread"])])
        assert 0 in p.gs.delivery_queue

    def test_no_active_stays_out(self):
        bots = [{"id": 0, "position": [5, 4], "inventory": ["bread"]}
                ] + [{"id": i, "position": [i + 2, 6], "inventory": []} for i in range(1, 5)]
        p = make_planner(bots=bots,
                         items=[{"id": "i0", "type": "cheese", "position": [8, 2]}],
                         orders=[_order(["cheese"])])
        assert 0 not in p.gs.delivery_queue

    def test_clears_on_order_change(self):
        bots = [{"id": i, "position": [i * 2 + 2, 4], "inventory": []} for i in range(4)]
        p = make_planner(bots=bots,
                         items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
                         orders=[_order(["cheese"], oid="order_1")])
        p.gs.last_active_order_id = "order_0"
        p.gs.delivery_queue = [0, 1, 2]
        p.gs.bot_tasks = {0: {"type": "deliver"}}
        p._check_order_transition()
        assert p.gs.delivery_queue == []
        assert p.gs.bot_tasks == {}

    def test_duplicate_only_carrier_drops_out_of_active_queue(self):
        bots = [
            {"id": 0, "position": [8, 4], "inventory": ["bread", "yogurt", "flour"]},
            {"id": 1, "position": [2, 7], "inventory": ["yogurt", "flour"]},
            {"id": 2, "position": [2, 8], "inventory": ["flour", "flour"]},
            {"id": 3, "position": [9, 4], "inventory": []},
        ]
        p = make_planner(
            bots=bots,
            items=[],
            orders=[_order(["bread", "yogurt", "yogurt", "flour"])],
        )

        assert p.active_on_shelves == 0
        assert p.bot_carried_active[0] == {
            "bread": 1, "yogurt": 1, "flour": 1,
        }
        assert p.bot_carried_active[1] == {"yogurt": 1}
        assert p.bot_carried_active[2] == {}
        assert p.bot_has_active[2] is False
        assert set(p.gs.delivery_queue) == {0, 1}
