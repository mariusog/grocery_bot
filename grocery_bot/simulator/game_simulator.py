"""GameSimulator — core simulation engine for testing bot performance."""

import random
import statistics
import time
from collections import defaultdict

import bot

from grocery_bot.simulator.map_generator import generate_store_layout, generate_orders
from grocery_bot.simulator.diagnostics import DiagnosticTracker


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

        # Generate map layout
        self.walls, self.shelf_positions, self.item_shelves, self.item_type_names = (
            generate_store_layout(width, height, num_item_types)
        )
        self.drop_off = [1, height - 2]
        self.spawn = [width - 2, height - 2]

        # Generate orders
        self.orders = generate_orders(self.rng, self.item_type_names, items_per_order)

        # Game state
        self.round = 0
        self.score = 0
        self.items_delivered = 0
        self.orders_completed = 0
        self.active_order_idx = 0

        # Bots
        self.bots = []
        for i in range(num_bots):
            self.bots.append({
                "id": i,
                "position": list(self.spawn),
                "inventory": [],
            })

        # Items currently on map
        self.items_on_map = []
        for i, (x, y, itype) in enumerate(self.item_shelves):
            self.items_on_map.append({
                "id": f"item_{i}",
                "type": itype,
                "position": [x, y],
            })
        self._next_item_id = len(self.item_shelves)

    def get_state(self):
        """Build game state dict matching the server format."""
        orders = []
        if self.active_order_idx < len(self.orders):
            active = {**self.orders[self.active_order_idx], "status": "active"}
            orders.append(active)
        if self.active_order_idx + 1 < len(self.orders):
            preview = {**self.orders[self.active_order_idx + 1], "status": "preview"}
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
            self._next_item_id += 1
            self.items_on_map.append({
                "id": f"item_{self._next_item_id}",
                "type": item["type"],
                "position": list(item["position"]),
            })

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
            needed = {}
            for item in order["items_required"]:
                needed[item] = needed.get(item, 0) + 1
            for item in order["items_delivered"]:
                needed[item] = needed.get(item, 0) - 1

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
            else:
                changed = False

    def is_over(self):
        return self.round >= self.max_rounds

    def run(self, verbose=False, profile=False, diagnose=False):
        """Run full game, return results dict."""
        bot.reset_state()
        timings = defaultdict(list) if profile else None
        tracker = DiagnosticTracker(self) if diagnose else None

        while not self.is_over():
            state = self.get_state()
            if not state["orders"]:
                break

            if tracker:
                tracker.pre_round(self)

            if profile:
                t0 = time.perf_counter()
            actions = bot.decide_actions(state)
            if profile:
                timings["decide_actions"].append(time.perf_counter() - t0)

            self.apply_actions(actions)

            if tracker:
                tracker.post_round(self, actions)

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
        if profile and timings:
            result["timings"] = _compute_timing_stats(timings)
        if tracker:
            result["diagnostics"] = tracker.get_results()
        if verbose:
            print(f"  Final: {result}")
        return result


def _compute_timing_stats(timings):
    """Compute timing statistics from profiled data."""
    timing_stats = {}
    for name, vals in timings.items():
        ms = [v * 1000 for v in vals]
        sorted_ms = sorted(ms)
        p99_idx = min(int(len(ms) * 0.99), len(ms) - 1)
        timing_stats[name] = {
            "calls": len(ms),
            "avg_ms": statistics.mean(ms),
            "max_ms": max(ms),
            "p99_ms": sorted_ms[p99_idx],
            "total_ms": sum(ms),
        }
    return timing_stats
