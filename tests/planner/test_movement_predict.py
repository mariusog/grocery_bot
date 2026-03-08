"""Unit tests for MovementMixin — pre-prediction and delivery targeting."""

from tests.conftest import make_planner
from tests.planner.conftest import _active_order


class TestPrePredict:
    def test_single_bot_no_predictions(self):
        """Single bot skips pre-prediction entirely."""
        planner = make_planner(
            bots=[{"id": 0, "position": [3, 3], "inventory": []}],
            items=[{"id": "i0", "type": "cheese", "position": [4, 2]}],
            orders=[_active_order(["cheese"])],
        )
        # After plan(), predictions should exist from _decide_bot
        assert 0 in planner.predicted

    def test_multi_bot_predictions_populated(self):
        """Multi-bot should have predictions for all bots."""
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
        assert 0 in planner.predicted
        assert 1 in planner.predicted

    def test_delivering_bot_predicts_toward_dropoff(self):
        """A delivering bot should predict movement toward dropoff."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [5, 3], "inventory": ["cheese", "milk", "bread"]},
                {"id": 1, "position": [7, 3], "inventory": []},
            ],
            items=[
                {"id": "i0", "type": "butter", "position": [4, 2]},
            ],
            orders=[_active_order(["cheese", "milk", "bread", "butter"])],
            drop_off=[1, 8],
        )
        # Bot 0 is full with active items -> delivering
        pred_0 = planner.predicted[0]
        # Predicted position should be closer to dropoff than current
        pos_0 = (5, 3)
        d_current = planner.gs.dist_static(pos_0, planner.drop_off)
        d_predicted = planner.gs.dist_static(pred_0, planner.drop_off)
        assert d_predicted <= d_current

    def test_extra_deliverer_targets_wait_cell_when_dropoff_is_crowded(self):
        """Only the front of the delivery pack should approach the dropoff directly."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [1, 8], "inventory": ["milk"]},
                {"id": 1, "position": [1, 7], "inventory": ["cheese"]},
                {"id": 2, "position": [2, 8], "inventory": ["bread"]},
                {"id": 3, "position": [5, 8], "inventory": ["yogurt"]},
            ],
            items=[],
            orders=[_active_order(["milk", "cheese", "bread", "yogurt"])],
            drop_off=[1, 8],
        )
        target, should_wait = planner._get_delivery_target(3, (5, 8))
        assert should_wait is True
        assert target != planner.drop_off

    def test_far_deliverer_keeps_direct_dropoff_target(self):
        """Far carriers should not stage at wait cells until they approach the zone."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [1, 8], "inventory": ["milk"]},
                {"id": 1, "position": [1, 7], "inventory": ["cheese"]},
                {"id": 2, "position": [2, 8], "inventory": ["bread"]},
                {"id": 3, "position": [8, 8], "inventory": ["yogurt"]},
            ],
            items=[],
            orders=[_active_order(["milk", "cheese", "bread", "yogurt"])],
            drop_off=[1, 8],
        )
        target, should_wait = planner._get_delivery_target(3, (8, 8))
        assert should_wait is False
        assert target == planner.drop_off

    def test_idle_near_dropoff_predicts_clearance_when_congested(self):
        """Idle bot near a congested dropoff should be predicted to clear out."""
        planner = make_planner(
            bots=[
                {"id": 0, "position": [1, 8], "inventory": ["milk"]},
                {"id": 1, "position": [1, 7], "inventory": ["cheese"]},
                {"id": 2, "position": [2, 8], "inventory": []},
                {"id": 3, "position": [5, 3], "inventory": []},
            ],
            items=[],
            orders=[_active_order(["milk", "cheese"])],
            drop_off=[1, 8],
        )
        pos_2 = (2, 8)
        pred_2 = planner.predicted[2]
        assert pred_2 != pos_2
        assert planner.gs.dist_static(pred_2, planner.drop_off) > planner.gs.dist_static(
            pos_2, planner.drop_off
        )
