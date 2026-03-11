"""Blacklist and bot-history tracking mixin for RoundPlanner."""

from collections import deque

from grocery_bot.constants import (
    BLACKLIST_EXPIRY_ROUNDS,
    BOT_HISTORY_MAXLEN,
    PICKUP_FAIL_BLACKLIST_THRESHOLD,
)
from grocery_bot.planner._base import PlannerBase


class BlacklistMixin(PlannerBase):
    """Mixin providing blacklist management and bot history tracking."""

    def _init_bot_history(self) -> None:
        """Initialize or validate bot history tracking."""

        for b in self.bots:
            bid: int = b["id"]
            pos: tuple[int, int] = tuple(b["position"])
            if bid not in self.gs.bot_history:
                self.gs.bot_history[bid] = deque(maxlen=BOT_HISTORY_MAXLEN)
            self.gs.bot_history[bid].append(pos)

    def _detect_pickup_failures(self) -> None:
        gs = self.gs
        for b in self.bots:
            bid: int = b["id"]
            if bid not in gs.last_pickup:
                continue
            last_item_id, last_inv_len = gs.last_pickup[bid]
            actual_pos = tuple(b["position"])

            # Check if bot is at the expected position — if not, this is a
            # desync (server didn't apply our action) and we should NOT count
            # the pickup failure.
            expected_pos = gs.last_expected_pos.get(bid)
            position_matches = expected_pos is None or actual_pos == expected_pos

            if len(b["inventory"]) <= last_inv_len:
                if position_matches:
                    gs.pickup_fail_count[last_item_id] = (
                        gs.pickup_fail_count.get(last_item_id, 0) + 1
                    )
                    if gs.pickup_fail_count[last_item_id] >= PICKUP_FAIL_BLACKLIST_THRESHOLD:
                        gs.blacklisted_items.add(last_item_id)
                        current_round = self.full_state.get("round", 0)
                        gs.blacklist_round[last_item_id] = current_round
                # else: desync detected, don't count failure
            else:
                gs.pickup_fail_count.pop(last_item_id, None)
            del gs.last_pickup[bid]

    def _expire_blacklists(self) -> None:
        """Remove blacklisted items whose expiry window has passed."""
        gs = self.gs
        current_round = self.full_state.get("round", 0)
        expired = [
            item_id
            for item_id, bl_round in gs.blacklist_round.items()
            if current_round - bl_round >= BLACKLIST_EXPIRY_ROUNDS
        ]
        for item_id in expired:
            gs.blacklisted_items.discard(item_id)
            del gs.blacklist_round[item_id]
            gs.pickup_fail_count.pop(item_id, None)
