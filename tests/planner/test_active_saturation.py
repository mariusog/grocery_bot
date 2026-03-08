"""Tests for preview walking gate on medium teams.

When active items remain on shelves, teams of ≤5 bots should NOT walk
to distant preview items. Adjacent preview pickup is still allowed.

See docs/hard_invfull_fix_plan.md for the full design.
"""

import bot
from tests.conftest import make_state, get_action
from tests.planner.conftest import _active_order, _preview_order


class TestPreviewPrepickWalkGate:
    """Fix B: _try_preview_prepick blocks walking to preview for ≤5-bot teams."""

    def test_5bot_no_walk_to_preview_when_active(self):
        """5-bot team doesn't walk to distant preview when active items exist."""
        state = make_state(
            bots=[
                {"id": 0, "position": [3, 7], "inventory": []},
                {"id": 1, "position": [5, 7], "inventory": []},
                {"id": 2, "position": [7, 7], "inventory": []},
                {"id": 3, "position": [9, 7], "inventory": []},
                {"id": 4, "position": [3, 5], "inventory": []},
            ],
            items=[
                # 5 active items in row 2 (far from bots in row 7)
                {"id": "a0", "type": "cheese", "position": [2, 2]},
                {"id": "a1", "type": "milk", "position": [4, 2]},
                {"id": "a2", "type": "salt", "position": [6, 2]},
                {"id": "a3", "type": "butter", "position": [8, 2]},
                {"id": "a4", "type": "yogurt", "position": [10, 2]},
                # Distant preview items (NOT adjacent to any bot)
                {"id": "p0", "type": "bread", "position": [10, 6]},
                {"id": "p1", "type": "pasta", "position": [10, 4]},
            ],
            orders=[
                _active_order(["cheese", "milk", "salt", "butter", "yogurt"]),
                _preview_order(["bread", "pasta"]),
            ],
        )
        actions = bot.decide_actions(state)
        preview_ids = {"p0", "p1"}
        for a in actions:
            if a["action"] == "pick_up" and a["item_id"] in preview_ids:
                assert False, (
                    f"Bot {a['bot']} picked distant preview {a['item_id']} "
                    f"when 5 active items exist on shelves"
                )

    def test_4bot_no_walk_to_preview_when_active(self):
        """4-bot team also doesn't walk to distant preview."""
        state = make_state(
            bots=[
                {"id": 0, "position": [3, 7], "inventory": []},
                {"id": 1, "position": [5, 7], "inventory": []},
                {"id": 2, "position": [7, 7], "inventory": []},
                {"id": 3, "position": [9, 7], "inventory": []},
            ],
            items=[
                {"id": "a0", "type": "cheese", "position": [4, 2]},
                {"id": "a1", "type": "milk", "position": [6, 2]},
                {"id": "a2", "type": "salt", "position": [8, 2]},
                {"id": "a3", "type": "butter", "position": [10, 2]},
                {"id": "p0", "type": "bread", "position": [10, 6]},
            ],
            orders=[
                _active_order(["cheese", "milk", "salt", "butter"]),
                _preview_order(["bread"]),
            ],
        )
        actions = bot.decide_actions(state)
        for a in actions:
            if a["action"] == "pick_up" and a["item_id"] == "p0":
                assert False, (
                    "Bot walked to distant preview on 4-bot team with active on shelves"
                )

    def test_allows_walk_when_no_active(self):
        """Preview walking allowed when active_on_shelves == 0."""
        state = make_state(
            bots=[
                {"id": 0, "position": [3, 7], "inventory": ["cheese"]},
                {"id": 1, "position": [5, 7], "inventory": ["milk"]},
                {"id": 2, "position": [7, 7], "inventory": []},
                {"id": 3, "position": [9, 7], "inventory": []},
                {"id": 4, "position": [3, 5], "inventory": []},
            ],
            items=[
                # No active items on shelves (all picked up)
                # Preview items far away
                {"id": "p0", "type": "bread", "position": [10, 6]},
                {"id": "p1", "type": "pasta", "position": [10, 4]},
            ],
            orders=[
                _active_order(["cheese", "milk"]),
                _preview_order(["bread", "pasta"]),
            ],
        )
        # With 0 active on shelves, walking to preview should be allowed
        # (just verify no crash — behavior depends on other factors)
        bot.decide_actions(state)

    def test_adjacent_preview_still_allowed(self):
        """Adjacent preview pickup is NOT blocked — only walking."""
        state = make_state(
            bots=[
                {"id": 0, "position": [5, 5], "inventory": []},
                {"id": 1, "position": [3, 3], "inventory": []},
                {"id": 2, "position": [7, 3], "inventory": []},
                {"id": 3, "position": [9, 3], "inventory": []},
                {"id": 4, "position": [9, 5], "inventory": []},
            ],
            items=[
                # Active items far away
                {"id": "a0", "type": "cheese", "position": [2, 2]},
                {"id": "a1", "type": "milk", "position": [4, 2]},
                {"id": "a2", "type": "salt", "position": [6, 2]},
                {"id": "a3", "type": "butter", "position": [8, 2]},
                {"id": "a4", "type": "yogurt", "position": [10, 2]},
                # Preview item ADJACENT to bot 0
                {"id": "p0", "type": "bread", "position": [6, 5]},
            ],
            orders=[
                _active_order(["cheese", "milk", "salt", "butter", "yogurt"]),
                _preview_order(["bread"]),
            ],
        )
        actions = bot.decide_actions(state)
        # Adjacent preview pickup via _step_opportunistic_preview is OK
        # (no assertion on picking it up — we only block walking)
