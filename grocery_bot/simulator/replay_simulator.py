"""ReplaySimulator — loads a recorded map instead of generating one."""

import hashlib
import json
import random

from grocery_bot.simulator.game_simulator import GameSimulator
from grocery_bot.simulator.map_generator import generate_orders
from grocery_bot.simulator.presets import DIFFICULTY_PRESETS

DEFAULT_REPLAY_TOTAL_ORDERS = 50


def _matching_preset(recorded):
    """Return the difficulty preset matching the recorded map, if any."""
    for cfg in DIFFICULTY_PRESETS.values():
        if (
            cfg["width"] == recorded["grid"]["width"]
            and cfg["height"] == recorded["grid"]["height"]
            and cfg["num_bots"] == recorded["num_bots"]
        ):
            return cfg
    return None


def _default_total_orders(recorded):
    """Infer the live total-order count when older recordings omitted it."""
    preset = _matching_preset(recorded)
    if preset is not None and preset.get("max_rounds", 0) >= 500:
        return 100
    return DEFAULT_REPLAY_TOTAL_ORDERS


def _infer_items_per_order(recorded):
    """Infer the synthetic padding order size range for a recorded map."""
    preset = _matching_preset(recorded)
    if preset is not None:
        return preset["items_per_order"]

    sizes = [
        len(order.get("items_required", []))
        for order in recorded.get("orders", [])
        if order.get("items_required")
    ]
    if sizes:
        return (min(sizes), max(sizes))
    return (3, 4)


def _padding_seed(recorded):
    """Build a stable seed from the static map layout, independent of seen orders."""
    payload = {
        "grid": recorded["grid"],
        "drop_off": recorded["drop_off"],
        "spawn": recorded["spawn"],
        "num_bots": recorded["num_bots"],
        "items": recorded["items"],
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).digest()
    return int.from_bytes(digest[:8], "big")


class ReplaySimulator(GameSimulator):
    """Simulator that loads a recorded map for deterministic replay.

    Reuses all game physics from GameSimulator (apply_actions, _do_dropoff,
    _is_blocked, get_state, run) but loads map layout and order sequence
    from a JSON recording.
    """

    def __init__(self, map_path, pad_orders=True, total_orders=None):
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
        zones = recorded.get("drop_off_zones")
        self.drop_off_zones = (
            [list(z) for z in zones] if zones else [self.drop_off]
        )
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

        # Orders from recording, optionally extended with deterministic padding.
        self.orders = []
        for order in recorded.get("orders", []):
            self.orders.append({
                "id": order["id"],
                "items_required": list(order["items_required"]),
                "items_delivered": [],
                "complete": False,
            })

        self.recorded_order_count = len(self.orders)
        requested_total = recorded.get("total_orders", total_orders)
        if requested_total is None:
            requested_total = _default_total_orders(recorded)
        self.total_orders = max(self.recorded_order_count, requested_total)
        self.synthetic_order_count = 0

        if pad_orders and self.recorded_order_count < self.total_orders:
            items_per_order = _infer_items_per_order(recorded)
            synthetic_rng = random.Random(_padding_seed(recorded))
            synthetic_orders = generate_orders(
                synthetic_rng,
                self.item_type_names,
                items_per_order,
                count=self.total_orders,
            )
            for idx in range(self.recorded_order_count, self.total_orders):
                generated = synthetic_orders[idx]
                self.orders.append({
                    "id": f"order_{idx}",
                    "items_required": list(generated["items_required"]),
                    "items_delivered": [],
                    "complete": False,
                })
            self.synthetic_order_count = self.total_orders - self.recorded_order_count

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
