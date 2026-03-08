"""Tests for preview walker limits — tail bots should be active on large teams."""

from tests.conftest import make_planner
from tests.planner.conftest import _active_order, _preview_order


class TestPreviewWalkerLimit:
    """Preview walker limit should allow all idle bots to walk."""

    def test_20bot_tail_bots_get_to_walk(self):
        """On 20-bot teams, ALL idle bots should be allowed to preview-walk."""
        bots = [{"id": i, "position": [i + 1, 4], "inventory": []} for i in range(20)]
        planner = make_planner(
            bots=bots,
            items=[
                {"id": f"i{i}", "type": f"t{i}", "position": [4 + (i % 6) * 2, 2]}
                for i in range(6)
            ] + [
                {"id": f"p{i}", "type": f"p{i}", "position": [4 + (i % 6) * 2, 6]}
                for i in range(8)
            ],
            orders=[
                _active_order([f"t{i}" for i in range(6)]),
                _preview_order([f"p{i}" for i in range(8)]),
            ],
            drop_off=[1, 8],
            width=30,
            height=18,
        )
        # On 20-bot teams, the preview walker limit should allow
        # enough walkers for all idle bots (no tail bots left idle).
        # Check that at least 14 bots received a non-wait action.
        non_wait = sum(
            1 for a in planner.actions if a["action"] != "wait"
        )
        assert non_wait >= 14, (
            f"Only {non_wait} bots got non-wait actions on 20-bot team. "
            f"Tail bots are being left idle. "
            f"Actions: {[(a['bot'], a['action']) for a in planner.actions]}"
        )

    def test_10bot_walker_limit_reasonable(self):
        """10-bot teams should still have a reasonable walker limit."""
        bots = [{"id": i, "position": [i + 1, 4], "inventory": []} for i in range(10)]
        planner = make_planner(
            bots=bots,
            items=[
                {"id": f"i{i}", "type": f"t{i}", "position": [4 + i * 2, 2]}
                for i in range(4)
            ] + [
                {"id": f"p{i}", "type": f"p{i}", "position": [4 + i * 2, 6]}
                for i in range(6)
            ],
            orders=[
                _active_order([f"t{i}" for i in range(4)]),
                _preview_order([f"p{i}" for i in range(6)]),
            ],
            drop_off=[1, 8],
            width=28,
            height=18,
        )
        # At least 7 out of 10 bots should get non-wait actions
        non_wait = sum(
            1 for a in planner.actions if a["action"] != "wait"
        )
        assert non_wait >= 7, (
            f"Only {non_wait}/10 bots active. Too restrictive walker limit."
        )
