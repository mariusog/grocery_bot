"""Local game simulator for testing bot performance without the live server.

Generates a realistic store layout matching the Easy map format and runs
the bot's decide_actions() through 300 rounds, tracking score and orders.
"""

import random

import bot


class GameSimulator:
    """Simulates the grocery bot game locally."""

    def __init__(
        self,
        seed=42,
        num_bots=1,
        width=12,
        height=10,
        num_item_types=4,
        items_per_order=(3, 4),
        max_rounds=300,
    ):
        self.rng = random.Random(seed)
        self.width = width
        self.height = height
        self.max_rounds = max_rounds
        self.num_bots = num_bots
        self.items_per_order = items_per_order
        self.item_type_names = [
            "milk",
            "cheese",
            "bread",
            "yogurt",
            "butter",
            "eggs",
            "pasta",
            "juice",
            "rice",
            "flour",
            "sugar",
            "salt",
            "oil",
            "vinegar",
            "honey",
            "tea",
        ][:num_item_types]

        # Generate map layout
        self.walls = []
        self.shelf_positions = set()  # permanent impassable positions
        self.item_shelves = []  # (x, y, type) — item placements
        self.drop_off = [1, height - 2]
        self.spawn = [width - 2, height - 2]

        self._generate_map()
        self._generate_orders(count=50)

        # Game state
        self.round = 0
        self.score = 0
        self.items_delivered = 0
        self.orders_completed = 0
        self.active_order_idx = 0

        # Bots
        self.bots = []
        for i in range(num_bots):
            self.bots.append(
                {
                    "id": i,
                    "position": list(self.spawn),
                    "inventory": [],
                }
            )

        # Items currently on map (restocked after pickup)
        self.items_on_map = []
        for i, (x, y, itype) in enumerate(self.item_shelves):
            self.items_on_map.append(
                {
                    "id": f"item_{i}",
                    "type": itype,
                    "position": [x, y],
                }
            )
        self._next_item_id = len(self.item_shelves)

    def _generate_map(self):
        """Generate a realistic store with vertical aisles.

        Layout pattern (Easy 12x10):
          - Horizontal corridors at y=1, y=4-5, y=7-8
          - Vertical shelf columns with walkways between them
          - Aisles: shelf-walkway-shelf (3 cells wide)
        """
        # Aisle configuration based on map size
        if self.width <= 12:
            aisle_starts = [2, 7]  # 2 aisles
        elif self.width <= 16:
            aisle_starts = [2, 6, 11]  # 3 aisles
        elif self.width <= 22:
            aisle_starts = [2, 6, 11, 16]  # 4 aisles
        else:
            aisle_starts = [2, 6, 11, 16, 21]  # 5 aisles

        # Shelf columns: each aisle has left shelf, walkway, right shelf
        shelf_cols = []
        for ax in aisle_starts:
            shelf_cols.append(ax)  # left shelf column
            shelf_cols.append(ax + 2)  # right shelf column

        # Shelf rows: skip corridor rows
        corridor_rows = {1, self.height - 3, self.height - 2}
        # Add mid-corridor
        mid = self.height // 2
        corridor_rows.add(mid)
        if self.height > 10:
            corridor_rows.add(mid - 1)

        shelf_rows = [y for y in range(2, self.height - 2) if y not in corridor_rows]

        # Place items on shelves, cycling through item types
        type_idx = 0
        for col in shelf_cols:
            for row in shelf_rows:
                if col < self.width - 1:
                    itype = self.item_type_names[type_idx % len(self.item_type_names)]
                    self.item_shelves.append((col, row, itype))
                    self.shelf_positions.add((col, row))
                    type_idx += 1

    def _generate_orders(self, count=50):
        """Generate random orders using available item types."""
        self.orders = []
        for i in range(count):
            lo, hi = self.items_per_order
            num_items = self.rng.randint(lo, hi)
            items = [self.rng.choice(self.item_type_names) for _ in range(num_items)]
            self.orders.append(
                {
                    "id": f"order_{i}",
                    "items_required": items,
                    "items_delivered": [],
                    "complete": False,
                }
            )

    def get_state(self):
        """Build game state dict matching the server format."""
        orders = []
        if self.active_order_idx < len(self.orders):
            active = {
                **self.orders[self.active_order_idx],
                "status": "active",
            }
            orders.append(active)
        if self.active_order_idx + 1 < len(self.orders):
            preview = {
                **self.orders[self.active_order_idx + 1],
                "status": "preview",
            }
            orders.append(preview)

        return {
            "type": "game_state",
            "round": self.round,
            "max_rounds": self.max_rounds,
            "grid": {
                "width": self.width,
                "height": self.height,
                "walls": [list(w) for w in self.walls],
            },
            "bots": [
                {
                    "id": b["id"],
                    "position": list(b["position"]),
                    "inventory": list(b["inventory"]),
                }
                for b in self.bots
            ],
            "items": [
                {"id": it["id"], "type": it["type"], "position": list(it["position"])}
                for it in self.items_on_map
            ],
            "orders": orders,
            "drop_off": list(self.drop_off),
            "score": self.score,
            "active_order_index": self.active_order_idx,
            "total_orders": len(self.orders),
        }

    def apply_actions(self, actions):
        """Apply bot actions, resolving in bot ID order."""
        actions_by_bot = {a["bot"]: a for a in actions}

        for b in sorted(self.bots, key=lambda b: b["id"]):
            action = actions_by_bot.get(b["id"], {"action": "wait"})
            self._apply_action(b, action)

        self.round += 1

    def _is_blocked(self, x, y, exclude_bot_id=None):
        """Check if a position is impassable."""
        if x < 0 or x >= self.width or y < 0 or y >= self.height:
            return True
        if (x, y) in self.shelf_positions:
            return True
        if [x, y] in self.walls:
            return True
        for b in self.bots:
            if b["id"] != exclude_bot_id and b["position"] == [x, y]:
                return True
        return False

    def _apply_action(self, b, action):
        act = action["action"]
        bx, by = b["position"]

        if act.startswith("move_"):
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

        elif act == "pick_up":
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

            # Restock: place a new item of the same type on the same shelf
            self._next_item_id += 1
            self.items_on_map.append(
                {
                    "id": f"item_{self._next_item_id}",
                    "type": item["type"],
                    "position": list(item["position"]),
                }
            )

        elif act == "drop_off":
            if b["position"] != list(self.drop_off):
                return
            if not b["inventory"]:
                return
            self._do_dropoff(b)

    def _do_dropoff(self, b):
        """Handle dropoff with cascade delivery across order transitions."""
        changed = True
        while changed and self.active_order_idx < len(self.orders):
            changed = False
            order = self.orders[self.active_order_idx]

            # Calculate what's still needed
            needed = {}
            for item in order["items_required"]:
                needed[item] = needed.get(item, 0) + 1
            for item in order["items_delivered"]:
                needed[item] = needed.get(item, 0) - 1

            # Deliver matching items from inventory
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

            # Check if order is complete
            req_counts = {}
            for it in order["items_required"]:
                req_counts[it] = req_counts.get(it, 0) + 1
            del_counts = {}
            for it in order["items_delivered"]:
                del_counts[it] = del_counts.get(it, 0) + 1

            if req_counts == del_counts:
                order["complete"] = True
                self.score += 5
                self.orders_completed += 1
                self.active_order_idx += 1
                # Continue loop to cascade-deliver remaining items
            else:
                changed = False

    def is_over(self):
        return self.round >= self.max_rounds

    def run(self, verbose=False):
        """Run full game, return results dict."""
        # Reset bot globals
        bot._blocked_static = None
        bot._dist_cache = {}
        bot._adj_cache = {}

        while not self.is_over():
            state = self.get_state()

            if not state["orders"]:
                break  # no more orders

            actions = bot.decide_actions(state)
            self.apply_actions(actions)

            if verbose and self.round % 50 == 0:
                print(
                    f"  Round {self.round}: score={self.score}, "
                    f"orders={self.orders_completed}, "
                    f"items={self.items_delivered}"
                )

        result = {
            "score": self.score,
            "items_delivered": self.items_delivered,
            "orders_completed": self.orders_completed,
            "rounds_used": self.round,
        }
        if verbose:
            print(f"  Final: {result}")
        return result
