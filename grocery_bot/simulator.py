"""Local game simulator for testing bot performance without the live server.

Generates a realistic store layout matching the Easy map format and runs
the bot's decide_actions() through 300 rounds, tracking score and orders.

Difficulty presets:
  Easy:   1 bot,  12x10 grid, 4 item types
  Medium: 3 bots, 16x12 grid, 8 item types
  Hard:   5 bots, 22x14 grid, 12 item types
  Expert: 10 bots, 28x18 grid, 16 item types
"""

import random
import statistics
import time
from collections import defaultdict

import bot


# --- Difficulty presets ---
DIFFICULTY_PRESETS = {
    "Easy": {
        "num_bots": 1,
        "width": 12,
        "height": 10,
        "num_item_types": 4,
        "items_per_order": (3, 4),
        "max_rounds": 300,
    },
    "Medium": {
        "num_bots": 3,
        "width": 16,
        "height": 12,
        "num_item_types": 8,
        "items_per_order": (3, 5),
        "max_rounds": 300,
    },
    "Hard": {
        "num_bots": 5,
        "width": 22,
        "height": 14,
        "num_item_types": 12,
        "items_per_order": (3, 5),
        "max_rounds": 300,
    },
    "Expert": {
        "num_bots": 10,
        "width": 28,
        "height": 18,
        "num_item_types": 16,
        "items_per_order": (4, 6),
        "max_rounds": 300,
    },
    "Nightmare": {
        "num_bots": 20,
        "width": 30,
        "height": 18,
        "num_item_types": 21,
        "items_per_order": (4, 6),
        "max_rounds": 500,
    },
}


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
        """Generate a store layout with border walls, vertical aisles, and
        internal walls matching the live server structure.

        Live server wall counts: Easy ~44, Medium ~76, Hard ~108, Expert ~160.
        These include border walls + aisle end-cap walls.
        """
        # --- Border walls (top, bottom, left, right) ---
        for x in range(self.width):
            self.walls.append((x, 0))
            self.walls.append((x, self.height - 1))
        for y in range(1, self.height - 1):
            self.walls.append((0, y))
            self.walls.append((self.width - 1, y))

        wall_set = set(self.walls)

        # --- Aisle configuration based on map size ---
        if self.width <= 12:
            aisle_starts = [3, 7]  # 2 aisles
        elif self.width <= 16:
            aisle_starts = [3, 7, 11]  # 3 aisles
        elif self.width <= 22:
            aisle_starts = [3, 7, 11, 16]  # 4 aisles
        else:
            aisle_starts = [3, 7, 11, 16, 21]  # 5 aisles

        # Shelf columns: each aisle has left shelf, walkway, right shelf
        shelf_cols = []
        for ax in aisle_starts:
            shelf_cols.append(ax)  # left shelf column
            shelf_cols.append(ax + 2)  # right shelf column

        # Shelf rows: skip corridor rows
        corridor_rows = {1, self.height - 2}
        # Add mid-corridor(s)
        mid = self.height // 2
        corridor_rows.add(mid)
        if self.height > 10:
            corridor_rows.add(mid - 1)

        shelf_rows = [y for y in range(2, self.height - 2) if y not in corridor_rows]

        # --- Place shelves and items ---
        type_idx = 0
        for col in shelf_cols:
            for row in shelf_rows:
                if col < self.width - 1 and (col, row) not in wall_set:
                    itype = self.item_type_names[type_idx % len(self.item_type_names)]
                    self.item_shelves.append((col, row, itype))
                    self.shelf_positions.add((col, row))
                    type_idx += 1

        # --- Internal walls: mid-aisle barriers ---
        # Add walls between shelf blocks at the mid-corridor to create
        # realistic chokepoints. Bots must navigate around shelf groups.
        for ax in aisle_starts:
            for cap_col in [ax, ax + 2]:
                for crow in corridor_rows:
                    if crow <= 1 or crow >= self.height - 2:
                        continue  # don't block top/bottom corridors
                    if (cap_col, crow) not in wall_set and (
                        cap_col,
                        crow,
                    ) not in self.shelf_positions:
                        self.walls.append((cap_col, crow))
                        wall_set.add((cap_col, crow))

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

    def run(self, verbose=False, profile=False, diagnose=False):
        """Run full game, return results dict.

        Args:
            verbose: Print progress every 50 rounds.
            profile: If True, record per-function timing stats in result.
            diagnose: If True, track congestion diagnostics (idle, stuck,
                delivery gaps, oscillations) and include a 'diagnostics'
                key in the result dict.
        """
        bot.reset_state()

        timings = defaultdict(list) if profile else None

        # Diagnostic tracking state
        if diagnose:
            diag_idle_rounds = 0
            diag_stuck_rounds = 0
            diag_oscillation_count = 0
            diag_last_delivery_round = 0
            diag_max_delivery_gap = 0
            diag_idle_per_round = []
            # Track per-bot position history: bot_id -> [pos_round_n-2, pos_round_n-1]
            diag_prev_positions = {b["id"]: [] for b in self.bots}
            prev_score = 0
            prev_items_delivered = 0
            prev_orders_completed = 0
            # Action counts
            diag_moves = 0
            diag_waits = 0
            diag_pickups = 0
            diag_delivers = 0
            # Useful vs wasted pickups
            diag_useful_pickups = 0
            diag_wasted_pickups = 0
            # Inventory-full waits (bot waits with 3/3 inventory)
            diag_inv_full_waits = 0
            # Per-bot idle tracking
            diag_per_bot_idle = defaultdict(int)
            # Rounds per completed order tracking
            diag_order_start_round = self.round
            diag_rounds_per_order = []

        while not self.is_over():
            state = self.get_state()

            if not state["orders"]:
                break  # no more orders

            if profile:
                t0 = time.perf_counter()

            actions = bot.decide_actions(state)

            if profile:
                timings["decide_actions"].append(time.perf_counter() - t0)

            # Snapshot positions and state before applying actions
            if diagnose:
                pre_positions = {b["id"]: tuple(b["position"]) for b in self.bots}
                pre_inv_sizes = {b["id"]: len(b["inventory"]) for b in self.bots}
                # Capture active order needed items BEFORE actions
                diag_active_needed = set()
                if self.active_order_idx < len(self.orders):
                    _order = self.orders[self.active_order_idx]
                    _needed = {}
                    for _it in _order["items_required"]:
                        _needed[_it] = _needed.get(_it, 0) + 1
                    for _it in _order["items_delivered"]:
                        _needed[_it] = _needed.get(_it, 0) - 1
                    diag_active_needed = {k for k, v in _needed.items() if v > 0}
                # Snapshot items on map for pickup type lookup after apply
                diag_items_snapshot = {
                    it["id"]: it["type"] for it in self.items_on_map
                }

            self.apply_actions(actions)

            # Diagnostic collection after actions applied
            if diagnose:
                actions_by_bot = {a["bot"]: a for a in actions}
                round_idle = 0

                for b in self.bots:
                    bid = b["id"]
                    action = actions_by_bot.get(bid, {"action": "wait"})
                    act = action["action"]
                    cur_pos = tuple(b["position"])
                    prev_pos = pre_positions[bid]

                    # Action counting
                    if act.startswith("move_"):
                        diag_moves += 1
                    elif act == "wait":
                        diag_waits += 1
                    elif act == "pick_up":
                        diag_pickups += 1
                        # Check if pickup is for active order (using pre-action snapshot)
                        item_id = action.get("item_id")
                        picked_type = diag_items_snapshot.get(item_id)
                        if picked_type and picked_type in diag_active_needed:
                            diag_useful_pickups += 1
                        else:
                            diag_wasted_pickups += 1
                    elif act == "drop_off":
                        diag_delivers += 1

                    # Idle detection: explicit wait action
                    if act == "wait":
                        diag_idle_rounds += 1
                        diag_per_bot_idle[bid] += 1
                        round_idle += 1
                        # Inventory-full wait (check pre-action inventory)
                        if pre_inv_sizes[bid] >= 3:
                            diag_inv_full_waits += 1

                    # Stuck detection: position unchanged after a move attempt
                    if cur_pos == prev_pos and act.startswith("move_"):
                        diag_stuck_rounds += 1

                    # Oscillation detection: returned to position from 2 rounds ago
                    history = diag_prev_positions[bid]
                    if len(history) >= 2 and cur_pos == history[-2]:
                        diag_oscillation_count += 1

                    # Update position history (keep last 2)
                    history.append(cur_pos)
                    if len(history) > 2:
                        history.pop(0)

                diag_idle_per_round.append(round_idle)

                # Track order completion rounds
                if self.orders_completed > prev_orders_completed:
                    new_completions = self.orders_completed - prev_orders_completed
                    for _ in range(new_completions):
                        diag_rounds_per_order.append(
                            self.round - diag_order_start_round
                        )
                        diag_order_start_round = self.round
                    prev_orders_completed = self.orders_completed

                # Delivery gap tracking
                if self.score > prev_score:
                    gap = self.round - diag_last_delivery_round
                    if gap > diag_max_delivery_gap:
                        diag_max_delivery_gap = gap
                    diag_last_delivery_round = self.round
                prev_score = self.score
                prev_items_delivered = self.items_delivered

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
            result["timings"] = timing_stats
        if diagnose:
            total_bot_rounds = self.round * len(self.bots)
            # Final delivery gap: from last delivery to end
            final_gap = self.round - diag_last_delivery_round
            if final_gap > diag_max_delivery_gap:
                diag_max_delivery_gap = final_gap
            total_pickups = diag_useful_pickups + diag_wasted_pickups
            avg_rounds_per_order = (
                statistics.mean(diag_rounds_per_order)
                if diag_rounds_per_order
                else 0.0
            )
            pickup_delivery_ratio = (
                total_pickups / self.items_delivered
                if self.items_delivered > 0
                else 0.0
            )
            result["diagnostics"] = {
                # Existing metrics
                "idle_rounds": diag_idle_rounds,
                "stuck_rounds": diag_stuck_rounds,
                "max_delivery_gap": diag_max_delivery_gap,
                "oscillation_count": diag_oscillation_count,
                "avg_bots_idle": (
                    statistics.mean(diag_idle_per_round) if diag_idle_per_round else 0.0
                ),
                "total_bot_rounds": total_bot_rounds,
                # Action counts
                "moves": diag_moves,
                "waits": diag_waits,
                "pickups": diag_pickups,
                "delivers": diag_delivers,
                # Pickup quality
                "useful_pickups": diag_useful_pickups,
                "wasted_pickups": diag_wasted_pickups,
                "pickup_waste_pct": (
                    diag_wasted_pickups / total_pickups * 100
                    if total_pickups > 0
                    else 0.0
                ),
                # Inventory-full waits
                "inv_full_waits": diag_inv_full_waits,
                # Order efficiency
                "avg_rounds_per_order": avg_rounds_per_order,
                "pickup_delivery_ratio": pickup_delivery_ratio,
                # Per-bot idle
                "per_bot_idle": dict(diag_per_bot_idle),
            }
        if verbose:
            print(f"  Final: {result}")
        return result


def run_benchmark(configs=None, seeds=None, verbose=False):
    """Run multiple simulator configurations and print a comparison table.

    Args:
        configs: dict of {name: kwargs_dict} for GameSimulator.
                 Defaults to DIFFICULTY_PRESETS.
        seeds: list of seeds to test per config. Defaults to [42].
        verbose: Print per-seed details.

    Returns:
        list of result dicts with config metadata.
    """
    if configs is None:
        configs = DIFFICULTY_PRESETS
    if seeds is None:
        seeds = [42]

    all_results = []
    print(
        f"{'Config':<10} {'Bots':>4} {'Seed':>5} {'Score':>6} "
        f"{'Orders':>7} {'Items':>6} {'Rounds':>7} {'Time(s)':>8}"
    )
    print("-" * 65)

    for cname, cfg in configs.items():
        config_scores = []
        for seed in seeds:
            t0 = time.perf_counter()
            sim = GameSimulator(seed=seed, **cfg)
            result = sim.run(verbose=verbose, profile=True)
            elapsed = time.perf_counter() - t0

            result["config"] = cname
            result["seed"] = seed
            result["num_bots"] = cfg.get("num_bots", 1)
            result["wall_time_s"] = elapsed
            all_results.append(result)
            config_scores.append(result["score"])

            print(
                f"{cname:<10} {cfg.get('num_bots', 1):>4} {seed:>5} "
                f"{result['score']:>6} {result['orders_completed']:>7} "
                f"{result['items_delivered']:>6} {result['rounds_used']:>7} "
                f"{elapsed:>8.3f}"
            )

        if len(seeds) > 1:
            avg = statistics.mean(config_scores)
            print(f"{'':10} {'':>4} {'AVG':>5} {avg:>6.1f}")

    return all_results


def profile_congestion(num_bots, seeds, verbose=False):
    """Run each seed with diagnostics and print a congestion profile table.

    Args:
        num_bots: Number of bots to simulate.
        seeds: List of seeds to test.
        verbose: Print per-round progress.

    Returns:
        List of result dicts (with diagnostics) for each seed.
    """
    cfg = dict(DIFFICULTY_PRESETS["Hard"])
    cfg["num_bots"] = num_bots

    all_results = []
    header = (
        f"{'Seed':>5} {'Score':>6} {'Orders':>7} {'Items':>6} "
        f"{'Idle%':>6} {'Stuck%':>7} {'MaxGap':>7} {'Oscil':>6} "
        f"{'AvgIdle':>8} {'Status'}"
    )
    print(f"\n=== Congestion Profile: {num_bots} bots ===")
    print(header)
    print("-" * len(header))

    for seed in seeds:
        sim = GameSimulator(seed=seed, **cfg)
        result = sim.run(verbose=verbose, diagnose=True)
        result["seed"] = seed
        result["num_bots"] = num_bots
        all_results.append(result)

        diag = result["diagnostics"]
        total_br = diag["total_bot_rounds"]
        idle_pct = (diag["idle_rounds"] / total_br * 100) if total_br > 0 else 0
        stuck_pct = (diag["stuck_rounds"] / total_br * 100) if total_br > 0 else 0

        # Flag problematic seeds
        problems = []
        if result["score"] < 50:
            problems.append("LOW_SCORE")
        if idle_pct > 30:
            problems.append("HIGH_IDLE")
        if stuck_pct > 10:
            problems.append("HIGH_STUCK")
        if diag["max_delivery_gap"] > 40:
            problems.append("LONG_GAP")
        if diag["oscillation_count"] > 20:
            problems.append("OSCILLATING")
        status = ", ".join(problems) if problems else "OK"

        print(
            f"{seed:>5} {result['score']:>6} {result['orders_completed']:>7} "
            f"{result['items_delivered']:>6} {idle_pct:>5.1f}% {stuck_pct:>6.1f}% "
            f"{diag['max_delivery_gap']:>7} {diag['oscillation_count']:>6} "
            f"{diag['avg_bots_idle']:>8.2f} {status}"
        )

    # Summary
    scores = [r["score"] for r in all_results]
    print(f"\n  Average score: {statistics.mean(scores):.1f}")
    print(f"  Min score: {min(scores)}, Max score: {max(scores)}")
    problem_seeds = [
        r["seed"]
        for r in all_results
        if r["score"] < 50
        or (
            r["diagnostics"]["idle_rounds"] / r["diagnostics"]["total_bot_rounds"] * 100
            > 30
        )
    ]
    if problem_seeds:
        print(f"  Problematic seeds: {problem_seeds}")
    else:
        print("  No problematic seeds detected.")

    return all_results
