"""ReplaySimulator — loads a recorded map instead of generating one."""

import json
import random

from grocery_bot.simulator.game_simulator import GameSimulator


class ReplaySimulator(GameSimulator):
    """Simulator that loads a recorded map for deterministic replay.

    Reuses all game physics from GameSimulator (apply_actions, _do_dropoff,
    _is_blocked, get_state, run) but loads map layout and order sequence
    from a JSON recording.
    """

    def __init__(self, map_path):
        # Skip GameSimulator.__init__ — we load everything from the recording
        with open(map_path) as f:
            recorded = json.load(f)

        self.width = recorded["grid"]["width"]
        self.height = recorded["grid"]["height"]
        self.max_rounds = recorded.get("max_rounds", 300)
        self.num_bots = recorded["num_bots"]
        self.rng = random.Random(0)
        self.items_per_order = (0, 0)

        self.walls = [list(w) for w in recorded["grid"]["walls"]]
        self.drop_off = list(recorded["drop_off"])
        self.spawn = list(recorded["spawn"])

        # Build shelf_positions and item_shelves from recorded items
        self.shelf_positions = set()
        self.item_shelves = []
        for it in recorded["items"]:
            pos = (it["position"][0], it["position"][1])
            self.shelf_positions.add(pos)
            self.item_shelves.append((pos[0], pos[1], it["type"]))

        self.items_on_map = []
        for it in recorded["items"]:
            self.items_on_map.append({
                "id": it["id"],
                "type": it["type"],
                "position": list(it["position"]),
            })
        self._next_item_id = len(recorded["items"])

        self.item_type_names = sorted({it["type"] for it in recorded["items"]})

        # Orders from recording, extended with generated orders
        self.orders = []
        for order in recorded.get("orders", []):
            self.orders.append({
                "id": order["id"],
                "items_required": list(order["items_required"]),
                "items_delivered": [],
                "complete": False,
            })

        order_rng = random.Random(recorded.get("map_seed", 42))
        if self.orders:
            sizes = [len(o["items_required"]) for o in self.orders]
            lo, hi = min(sizes), max(sizes)
        else:
            lo, hi = 3, 5
        n_existing = len(self.orders)
        for i in range(n_existing, 100):
            num_items = order_rng.randint(lo, hi)
            items = [order_rng.choice(self.item_type_names) for _ in range(num_items)]
            self.orders.append({
                "id": f"order_{i}",
                "items_required": items,
                "items_delivered": [],
                "complete": False,
            })

        # Game state
        self.round = 0
        self.score = 0
        self.items_delivered = 0
        self.orders_completed = 0
        self.active_order_idx = 0

        # Bots
        self.bots = []
        for i in range(self.num_bots):
            self.bots.append({
                "id": i,
                "position": list(self.spawn),
                "inventory": [],
            })
