"""Test that the bot handles WebSocket message desync scenarios.

Reproduces the live server bug where actions get offset by 1 round
after a drop_off, causing the bot to get permanently stuck.
"""

import csv
import os

import pytest


class TestActionPositionConsistency:
    """Verify that the action sent in round N produces the expected position in round N+1."""

    def _parse_log(self, log_path):
        """Parse a game CSV log into a list of row dicts."""
        with open(log_path) as f:
            return list(csv.DictReader(f))

    def _check_consistency(self, rows):
        """Return list of (round, action, expected_pos, actual_pos) for mismatches."""
        mismatches = []
        for i in range(len(rows) - 1):
            r = rows[i]
            r_next = rows[i + 1]
            rnd = int(r["round"])
            pos = r["bot_pos"]
            act = r["action"]
            next_pos = r_next["bot_pos"].strip()

            px, py = map(int, pos.split(","))
            if act == "move_right":
                ex, ey = px + 1, py
            elif act == "move_left":
                ex, ey = px - 1, py
            elif act == "move_up":
                ex, ey = px, py - 1
            elif act == "move_down":
                ex, ey = px, py + 1
            else:
                ex, ey = px, py

            expected = f"{ex},{ey}"
            if next_pos != expected:
                mismatches.append((rnd, act, expected, next_pos))
        return mismatches

    def test_simulator_actions_are_consistent(self):
        """Simulator should never have action-position mismatches."""
        import bot
        from grocery_bot.simulator import GameSimulator

        bot.reset_state()
        sim = GameSimulator(seed=42, num_bots=1, width=12, height=10)

        log_rows = []
        while not sim.is_over():
            state = sim.get_state()
            if not state["orders"]:
                break
            actions = bot.decide_actions(state)

            # Log the state and action
            b = state["bots"][0]
            log_rows.append(
                {
                    "round": state["round"],
                    "bot_pos": f"{b['position'][0]},{b['position'][1]}",
                    "action": actions[0]["action"],
                    "item_id": actions[0].get("item_id", ""),
                    "inventory": ";".join(b["inventory"]),
                }
            )
            sim.apply_actions(actions)

        mismatches = self._check_consistency(log_rows)
        assert mismatches == [], (
            f"Found {len(mismatches)} action-position mismatches in simulator: "
            f"first at round {mismatches[0][0]}: {mismatches[0][1]} "
            f"expected {mismatches[0][2]}, got {mismatches[0][3]}"
        )

    @pytest.mark.skipif(
        not os.path.exists("logs/game_20260307_144157.csv"),
        reason="Live game log not available",
    )
    @pytest.mark.xfail(reason="Known bug in pre-fix game log — desync at round 37")
    def test_live_game_log_has_no_desync(self):
        """The live game log should show no action-position desync.

        This test documents the WebSocket desync bug found in the
        pre-fix game log. The fix (round dedup guard) prevents this
        in future games.
        """
        rows = self._parse_log("logs/game_20260307_144157.csv")
        mismatches = self._check_consistency(rows)

        # This WILL fail on the known-broken log — that's the point.
        # The first mismatch is at round 37, right after a partial drop_off.
        if mismatches:
            first = mismatches[0]
            pytest.fail(
                f"Live game desync detected: {len(mismatches)} mismatches. "
                f"First at round {first[0]}: sent '{first[1]}', "
                f"expected pos {first[2]}, server reported {first[3]}. "
                f"This confirms the WebSocket message handling bug."
            )


class TestPickupAfterRestock:
    """Verify that items can be picked up after restocking."""

    def test_item_restock_uses_new_id(self):
        """After picking up an item, the restocked item has a new ID."""
        from grocery_bot.simulator import GameSimulator

        sim = GameSimulator(seed=42, num_bots=1, width=12, height=10)
        # Find an item and its position
        item = sim.items_on_map[0]
        item_id = item["id"]
        item_pos = list(item["position"])

        # Place bot adjacent to item
        bot_obj = sim.bots[0]
        bot_obj["position"] = [item_pos[0], item_pos[1] + 1]

        # Pick up
        sim.apply_actions([{"bot": 0, "action": "pick_up", "item_id": item_id}])

        # Old item_id should be gone
        current_ids = {it["id"] for it in sim.items_on_map}
        assert item_id not in current_ids, "Old item_id should be removed after pickup"

        # New item should exist at same position
        restocked = [it for it in sim.items_on_map if list(it["position"]) == item_pos]
        assert len(restocked) == 1, "Item should restock at same position"
        assert restocked[0]["id"] != item_id, "Restocked item should have new ID"
        assert restocked[0]["type"] == item["type"], "Restocked item should keep same type"

    def test_pickup_same_position_twice(self):
        """Bot should be able to pick up from same shelf position multiple times."""
        from grocery_bot.simulator import GameSimulator

        sim = GameSimulator(seed=42, num_bots=1, width=12, height=10)

        item = sim.items_on_map[0]
        item_pos = list(item["position"])
        item_type = item["type"]

        bot_obj = sim.bots[0]
        bot_obj["position"] = [item_pos[0], item_pos[1] + 1]

        # First pickup
        sim.apply_actions([{"bot": 0, "action": "pick_up", "item_id": item["id"]}])
        assert bot_obj["inventory"] == [item_type]

        # Find the restocked item
        restocked = [it for it in sim.items_on_map if list(it["position"]) == item_pos]
        assert len(restocked) == 1

        # Second pickup with NEW item id
        sim.apply_actions([{"bot": 0, "action": "pick_up", "item_id": restocked[0]["id"]}])
        assert bot_obj["inventory"] == [item_type, item_type]

    def test_pickup_old_id_after_restock_fails(self):
        """Trying to pick up with the OLD item_id after restock should fail.

        This is the key difference: our simulator correctly rejects stale IDs,
        but the bot might cache stale IDs if item tracking is wrong.
        """
        from grocery_bot.simulator import GameSimulator

        sim = GameSimulator(seed=42, num_bots=1, width=12, height=10)

        item = sim.items_on_map[0]
        old_id = item["id"]
        item_pos = list(item["position"])

        bot_obj = sim.bots[0]
        bot_obj["position"] = [item_pos[0], item_pos[1] + 1]

        # Pick up first time
        sim.apply_actions([{"bot": 0, "action": "pick_up", "item_id": old_id}])
        assert len(bot_obj["inventory"]) == 1

        # Try picking up with OLD id — should fail
        sim.apply_actions([{"bot": 0, "action": "pick_up", "item_id": old_id}])
        assert len(bot_obj["inventory"]) == 1, "Pickup with stale ID should fail"


class TestBlacklistDoesNotStickForever:
    """Blacklisting should not permanently block the only item of a needed type."""

    def test_blacklisted_item_blocks_pickup(self):
        """A blacklisted item should be skipped by the planner."""
        import bot
        from grocery_bot.planner.round_planner import RoundPlanner
        from tests.conftest import make_state

        bot.reset_state()

        state = make_state(
            bots=[{"id": 0, "position": [3, 7], "inventory": []}],
            items=[{"id": "item_12", "type": "yogurt", "position": [3, 6]}],
            orders=[
                {
                    "id": "o1",
                    "items_required": ["yogurt"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                }
            ],
        )

        bot.decide_actions(state)
        gs = bot._gs

        # Blacklist the only yogurt item
        gs.blacklisted_items.add("item_12")

        planner = RoundPlanner(gs, state, full_state=state)
        planner.plan()

        # The bot should NOT try to pick up the blacklisted item
        for action in planner.actions:
            assert action.get("item_id") != "item_12", (
                "Bot should not try to pick up a blacklisted item"
            )

    def test_only_item_of_type_blacklisted_causes_stuck(self):
        """When the only item of a needed type is blacklisted, bot gets stuck.

        This is the scenario from the live game: item_12 (yogurt) gets
        blacklisted, and it's the ONLY yogurt on the map. The bot can
        never complete the order.
        """
        import bot
        from grocery_bot.planner.round_planner import RoundPlanner
        from tests.conftest import make_state

        bot.reset_state()

        items = [
            {"id": "item_12", "type": "yogurt", "position": [3, 6]},
            {"id": "item_5", "type": "milk", "position": [5, 4]},
        ]
        state = make_state(
            bots=[{"id": 0, "position": [3, 7], "inventory": []}],
            items=items,
            orders=[
                {
                    "id": "o1",
                    "items_required": ["yogurt"],
                    "items_delivered": [],
                    "complete": False,
                    "status": "active",
                }
            ],
        )

        bot.decide_actions(state)
        gs = bot._gs
        gs.blacklisted_items.add("item_12")

        planner = RoundPlanner(gs, state, full_state=state)
        planner.plan()

        # Bot should still try to do SOMETHING useful (not just wait forever)
        action = planner.actions[0]
        # With yogurt blacklisted, the bot should at least not be stuck
        # trying to pick it up in a loop
        assert action.get("item_id") != "item_12"
