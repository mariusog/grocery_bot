"""GameSimulator — core simulation engine for testing bot performance."""

import csv
import glob
import json
import os
import random
import statistics
import time
from collections import defaultdict
from datetime import datetime

import bot
from grocery_bot.orders import get_needed_items

from grocery_bot.simulator.map_generator import generate_store_layout, generate_orders
from grocery_bot.simulator.diagnostics import DiagnosticTracker
from grocery_bot.simulator.presets import DIFFICULTY_PRESETS


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
        """Apply bot actions with simultaneous swap-collision detection.

        Moves are resolved in two passes:
        1. Compute intended destinations for all move actions.
        2. Block swaps (two bots trying to exchange positions) and
           target-collisions (two bots moving to the same cell), then
           apply remaining moves and non-move actions.
        """
        actions_by_bot = {a["bot"]: a for a in actions}

        # Pass 1: compute intended positions for movers
        move_deltas = {
            "move_up": (0, -1), "move_down": (0, 1),
            "move_left": (-1, 0), "move_right": (1, 0),
        }
        intended: dict[int, tuple[int, int]] = {}  # bot_id -> (nx, ny)
        for b in self.bots:
            act = actions_by_bot.get(b["id"], {"action": "wait"})["action"]
            if act in move_deltas:
                dx, dy = move_deltas[act]
                intended[b["id"]] = (b["position"][0] + dx, b["position"][1] + dy)

        # Pass 2: detect swap collisions and block both participants
        blocked_bots: set[int] = set()
        bot_positions = {b["id"]: tuple(b["position"]) for b in self.bots}
        for bid_a, dest_a in intended.items():
            for bid_b, dest_b in intended.items():
                if bid_a >= bid_b:
                    continue
                # Swap: A wants B's position and B wants A's position
                if dest_a == bot_positions[bid_b] and dest_b == bot_positions[bid_a]:
                    blocked_bots.add(bid_a)
                    blocked_bots.add(bid_b)

        # Apply actions, skipping blocked movers
        for b in sorted(self.bots, key=lambda b: b["id"]):
            bid = b["id"]
            action = actions_by_bot.get(bid, {"action": "wait"})
            if bid in blocked_bots and action["action"] in move_deltas:
                continue  # swap-blocked
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

    def run(self, verbose=False, profile=False, diagnose=False, log=False):
        """Run full game, return results dict."""
        bot.reset_state()
        timings = defaultdict(list) if profile else None
        tracker = DiagnosticTracker(self) if diagnose else None
        log_rows = [] if log else None

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

            if log_rows is not None:
                _log_round(state, actions, log_rows)

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
        if log_rows is not None:
            result["log_path"] = _save_local_log(self, log_rows)
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


_LOG_DIR = "logs"
_MAX_LOCAL_LOGS = 10


def _infer_difficulty_slug(sim):
    """Best-effort difficulty label for local replay/log filenames."""
    item_type_count = len(
        getattr(sim, "item_type_names", [])
        or {it["type"] for it in getattr(sim, "items_on_map", [])}
    )
    for name, cfg in DIFFICULTY_PRESETS.items():
        if (
            sim.width == cfg["width"]
            and sim.height == cfg["height"]
            and sim.num_bots == cfg["num_bots"]
            and sim.max_rounds == cfg["max_rounds"]
            and item_type_count == cfg["num_item_types"]
        ):
            return name.lower()
    return "custom"


def _log_round(state, actions, log_rows):
    """Record one round of actions in the same CSV format as live games."""
    active_o = next(
        (o for o in state["orders"] if o.get("status") == "active" and not o["complete"]),
        None,
    )
    preview_o = next((o for o in state["orders"] if o.get("status") == "preview"), None)
    for a in actions:
        b = next(bt for bt in state["bots"] if bt["id"] == a["bot"])
        log_rows.append({
            "round": state["round"],
            "score": state["score"],
            "order_idx": state.get("active_order_index", ""),
            "bot_id": a["bot"],
            "bot_pos": f"{b['position'][0]},{b['position'][1]}",
            "inventory": ";".join(b["inventory"]) if b["inventory"] else "",
            "action": a["action"],
            "item_id": a.get("item_id", ""),
            "active_needed": (
                ";".join(f"{k}:{v}" for k, v in get_needed_items(active_o).items())
                if active_o else ""
            ),
            "active_delivered": (
                ";".join(active_o["items_delivered"]) if active_o else ""
            ),
            "preview_needed": (
                ";".join(f"{k}:{v}" for k, v in get_needed_items(preview_o).items())
                if preview_o else ""
            ),
        })


def _save_local_log(sim, log_rows):
    """Save CSV + JSON for a local simulator run, pruning old logs."""
    os.makedirs(_LOG_DIR, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    difficulty = _infer_difficulty_slug(sim)
    prefix = f"local_{difficulty}_{sim.width}x{sim.height}_{sim.num_bots}bot_{timestamp}"
    csv_path = f"{_LOG_DIR}/{prefix}.csv"
    json_path = f"{_LOG_DIR}/{prefix}.json"

    # Write CSV
    fieldnames = [
        "round", "score", "order_idx", "bot_id", "bot_pos",
        "inventory", "action", "item_id", "active_needed",
        "active_delivered", "preview_needed",
    ]
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(log_rows)

    # Write meta JSON (same format as live games)
    item_types = sorted({it["type"] for it in sim.items_on_map})
    meta = {
        "timestamp": timestamp,
        "source": "local_simulator",
        "difficulty": difficulty,
        "grid": {
            "width": sim.width,
            "height": sim.height,
            "walls": len(sim.walls),
            "wall_positions": [list(w) for w in sim.walls],
        },
        "bots": sim.num_bots,
        "items_on_map": len(sim.items_on_map),
        "item_types": item_types,
        "item_positions": [
            {"type": it["type"], "position": list(it["position"])}
            for it in sim.items_on_map
        ],
        "drop_off": list(sim.drop_off),
        "max_rounds": sim.max_rounds,
        "total_orders": len(sim.orders),
        "spawn": list(sim.spawn),
        "result": {
            "score": sim.score,
            "rounds_used": sim.round,
            "items_delivered": sim.items_delivered,
            "orders_completed": sim.orders_completed,
        },
    }
    with open(json_path, "w") as f:
        json.dump(meta, f, indent=2)

    # Prune old local logs (keep only the latest _MAX_LOCAL_LOGS)
    local_csvs = sorted(glob.glob(f"{_LOG_DIR}/local_*.csv"))
    while len(local_csvs) > _MAX_LOCAL_LOGS:
        old_csv = local_csvs.pop(0)
        old_json = old_csv.replace(".csv", ".json")
        os.remove(old_csv)
        if os.path.exists(old_json):
            os.remove(old_json)

    return csv_path
