"""PhysicsMixin — movement, collision, pickup and dropoff logic."""

from typing import Any

from grocery_bot.simulator._base import SimulatorBase


class PhysicsMixin(SimulatorBase):
    """Mixin providing game physics for GameSimulator.

    Methods here handle bot movement validation, action application,
    swap-collision detection, and order delivery cascading.
    """

    def apply_actions(self, actions: list[dict[str, Any]]) -> None:
        """Apply bot actions sequentially by bot ID.

        The live server processes each bot in ID order (0, 1, 2, ...),
        updating positions in-place. Later bots see earlier bots' new
        positions, so higher-ID bots can follow lower-ID bots (chain
        moves) but not vice versa.
        """
        actions_by_bot = {a["bot"]: a for a in actions}
        for b in sorted(self.bots, key=lambda bot: bot["id"]):
            action = actions_by_bot.get(b["id"], {"action": "wait"})
            self._apply_action(b, action)
        self.round += 1

    def _is_blocked(self, x: int, y: int, exclude_bot_id: int | None = None) -> bool:
        """Check if a position is impassable."""
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return True
        if (x, y) in self.shelf_positions:
            return True
        if [x, y] in self.walls:
            return True
        return any(b["id"] != exclude_bot_id and b["position"] == [x, y] for b in self.bots)

    def _apply_action(self, b: dict, action: dict) -> None:
        """Apply a single bot's action to the game state."""
        act = action["action"]
        bx, by = b["position"]

        if act.startswith("move_"):
            self._apply_move(b, act, bx, by)
        elif act == "pick_up":
            self._apply_pickup(b, action, bx, by)
        elif act == "drop_off":
            if not any(b["position"] == list(z) for z in self.drop_off_zones):
                return
            if not b["inventory"]:
                return
            # Illegal move: drop_off with no matching active-order items
            # incurs a 10-second penalty on the live server (~2 lost rounds).
            if self.active_order_idx < len(self.orders):
                needed = _compute_needed(self.orders[self.active_order_idx])
                if not any(needed.get(item, 0) > 0 for item in b["inventory"]):
                    self._illegal_dropoff_count += 1
                    self.round += 2  # penalty: skip 2 rounds
                    return
            self._do_dropoff(b)

    def _apply_move(self, b: dict, act: str, bx: int, by: int) -> None:
        """Resolve a movement action for one bot."""
        dx, dy = 0, 0
        if act == "move_up":
            dy = -1
        elif act == "move_down":
            dy = 1
        elif act == "move_left":
            dx = -1
        elif act == "move_right":
            dx = 1
        nx, ny = bx + dx, by + dy
        if not self._is_blocked(nx, ny, exclude_bot_id=b["id"]):
            b["position"] = [nx, ny]

    def _apply_pickup(self, b: dict, action: dict, bx: int, by: int) -> None:
        """Resolve a pick-up action for one bot."""
        item_id = action.get("item_id")
        if not item_id or len(b["inventory"]) >= 3:
            return
        item = None
        for it in self.items_on_map:
            if it["id"] == item_id:
                item = it
                break
        if not item:
            return
        ix, iy = item["position"]
        if abs(bx - ix) + abs(by - iy) != 1:
            return
        b["inventory"].append(item["type"])
        self.items_on_map.remove(item)
        self._next_item_id += 1
        self.items_on_map.append(
            {
                "id": f"item_{self._next_item_id}",
                "type": item["type"],
                "position": list(item["position"]),
            }
        )

    def _do_dropoff(self, b: dict) -> None:
        """Handle dropoff with cascade delivery across order transitions."""
        changed = True
        while changed and self.active_order_idx < len(self.orders):
            changed = False
            order = self.orders[self.active_order_idx]
            needed = _compute_needed(order)

            new_inv = []
            for item in b["inventory"]:
                if needed.get(item, 0) > 0:
                    order["items_delivered"].append(item)
                    needed[item] -= 1
                    self.score += 1
                    self.items_delivered += 1
                    changed = True
                else:
                    new_inv.append(item)
            b["inventory"] = new_inv

            if _order_complete(order):
                order["complete"] = True
                self.score += 5
                self.orders_completed += 1
                self.active_order_idx += 1
            else:
                changed = False


def _compute_needed(order: dict) -> dict[str, int]:
    """Build a dict of remaining item counts for an order."""
    needed: dict[str, int] = {}
    for item in order["items_required"]:
        needed[item] = needed.get(item, 0) + 1
    for item in order["items_delivered"]:
        needed[item] = needed.get(item, 0) - 1
    return needed


def _order_complete(order: dict) -> bool:
    """Return True when every required item has been delivered."""
    req: dict[str, int] = {}
    for it in order["items_required"]:
        req[it] = req.get(it, 0) + 1
    delivered: dict[str, int] = {}
    for it in order["items_delivered"]:
        delivered[it] = delivered.get(it, 0) + 1
    return req == delivered
