"""Diagnostic tracking for game simulation analysis."""

import statistics
from collections import defaultdict


class DiagnosticTracker:
    """Tracks per-round diagnostics during a simulation run.

    Separates diagnostic concerns from the core simulation loop.
    """

    def __init__(self, sim):
        self.num_bots = len(sim.bots)
        self.idle_rounds = 0
        self.stuck_rounds = 0
        self.oscillation_count = 0
        self.last_delivery_round = 0
        self.max_delivery_gap = 0
        self.idle_per_round = []
        self.prev_positions = {b["id"]: [] for b in sim.bots}
        self.prev_score = 0
        self.prev_orders_completed = 0

        # Action counts
        self.moves = 0
        self.waits = 0
        self.pickups = 0
        self.delivers = 0

        # Pickup quality
        self.useful_pickups = 0
        self.wasted_pickups = 0

        # Inventory-full waits
        self.inv_full_waits = 0

        # Per-bot idle tracking
        self.per_bot_idle = defaultdict(int)

        # Order timing
        self.order_start_round = sim.round
        self.rounds_per_order = []

        # Per-bot action breakdown
        self.per_bot_moves: dict[int, int] = defaultdict(int)
        self.per_bot_pickups: dict[int, int] = defaultdict(int)
        self.per_bot_delivers: dict[int, int] = defaultdict(int)
        self.per_bot_stuck: dict[int, int] = defaultdict(int)

        # Delivery efficiency
        self.delivery_sizes: list[int] = []

        # Order completion timeline (absolute round numbers)
        self.order_completion_rounds: list[int] = []

        # Pre-round snapshots (set in pre_round)
        self._pre_positions = {}
        self._pre_inv_sizes = {}
        self._active_needed = set()
        self._items_snapshot = {}

    def pre_round(self, sim):
        """Snapshot state before actions are applied."""
        self._pre_positions = {b["id"]: tuple(b["position"]) for b in sim.bots}
        self._pre_inv_sizes = {b["id"]: len(b["inventory"]) for b in sim.bots}

        self._active_needed = set()
        if sim.active_order_idx < len(sim.orders):
            order = sim.orders[sim.active_order_idx]
            needed = {}
            for it in order["items_required"]:
                needed[it] = needed.get(it, 0) + 1
            for it in order["items_delivered"]:
                needed[it] = needed.get(it, 0) - 1
            self._active_needed = {k for k, v in needed.items() if v > 0}

        self._items_snapshot = {it["id"]: it["type"] for it in sim.items_on_map}

    def post_round(self, sim, actions):
        """Update diagnostics after actions are applied."""
        actions_by_bot = {a["bot"]: a for a in actions}
        round_idle = 0

        for b in sim.bots:
            bid = b["id"]
            action = actions_by_bot.get(bid, {"action": "wait"})
            act = action["action"]
            cur_pos = tuple(b["position"])
            prev_pos = self._pre_positions[bid]

            # Action counting (global + per-bot)
            if act.startswith("move_"):
                self.moves += 1
                self.per_bot_moves[bid] += 1
            elif act == "wait":
                self.waits += 1
            elif act == "pick_up":
                self.pickups += 1
                self.per_bot_pickups[bid] += 1
                item_id = action.get("item_id")
                picked_type = self._items_snapshot.get(item_id)
                if picked_type and picked_type in self._active_needed:
                    self.useful_pickups += 1
                else:
                    self.wasted_pickups += 1
            elif act == "drop_off":
                self.delivers += 1
                self.per_bot_delivers[bid] += 1
                delivered = self._pre_inv_sizes[bid] - len(b["inventory"])
                if delivered > 0:
                    self.delivery_sizes.append(delivered)

            # Idle detection
            if act == "wait":
                self.idle_rounds += 1
                self.per_bot_idle[bid] += 1
                round_idle += 1
                if self._pre_inv_sizes[bid] >= 3:
                    self.inv_full_waits += 1

            # Stuck detection (global + per-bot)
            if cur_pos == prev_pos and act.startswith("move_"):
                self.stuck_rounds += 1
                self.per_bot_stuck[bid] += 1

            # Oscillation detection
            history = self.prev_positions[bid]
            if len(history) >= 2 and cur_pos == history[-2]:
                self.oscillation_count += 1

            history.append(cur_pos)
            if len(history) > 2:
                history.pop(0)

        self.idle_per_round.append(round_idle)

        # Track order completions
        if sim.orders_completed > self.prev_orders_completed:
            new_completions = sim.orders_completed - self.prev_orders_completed
            for _ in range(new_completions):
                self.rounds_per_order.append(sim.round - self.order_start_round)
                self.order_completion_rounds.append(sim.round)
                self.order_start_round = sim.round
            self.prev_orders_completed = sim.orders_completed

        # Delivery gap tracking
        if sim.score > self.prev_score:
            gap = sim.round - self.last_delivery_round
            if gap > self.max_delivery_gap:
                self.max_delivery_gap = gap
            self.last_delivery_round = sim.round
        self.prev_score = sim.score

    def get_results(self):
        """Return diagnostics summary dict."""
        total_bot_rounds = (self.last_delivery_round or 1) + sum(
            1 for _ in self.idle_per_round
        ) - 1
        # More accurate: total_bot_rounds = rounds_used * num_bots
        total_bot_rounds = len(self.idle_per_round) * self.num_bots

        final_gap = len(self.idle_per_round) - self.last_delivery_round
        if final_gap > self.max_delivery_gap:
            self.max_delivery_gap = final_gap

        total_pickups = self.useful_pickups + self.wasted_pickups
        avg_rounds_per_order = (
            statistics.mean(self.rounds_per_order)
            if self.rounds_per_order
            else 0.0
        )
        items_delivered = self.prev_score  # approximate
        pickup_delivery_ratio = (
            total_pickups / max(1, items_delivered)
        )

        return {
            "idle_rounds": self.idle_rounds,
            "stuck_rounds": self.stuck_rounds,
            "max_delivery_gap": self.max_delivery_gap,
            "oscillation_count": self.oscillation_count,
            "avg_bots_idle": (
                statistics.mean(self.idle_per_round)
                if self.idle_per_round
                else 0.0
            ),
            "total_bot_rounds": total_bot_rounds,
            "moves": self.moves,
            "waits": self.waits,
            "pickups": self.pickups,
            "delivers": self.delivers,
            "useful_pickups": self.useful_pickups,
            "wasted_pickups": self.wasted_pickups,
            "pickup_waste_pct": (
                self.wasted_pickups / total_pickups * 100
                if total_pickups > 0
                else 0.0
            ),
            "inv_full_waits": self.inv_full_waits,
            "avg_rounds_per_order": avg_rounds_per_order,
            "pickup_delivery_ratio": pickup_delivery_ratio,
            "per_bot_idle": dict(self.per_bot_idle),
            "per_bot_actions": {
                bid: {
                    "moves": self.per_bot_moves[bid],
                    "pickups": self.per_bot_pickups[bid],
                    "delivers": self.per_bot_delivers[bid],
                    "stuck": self.per_bot_stuck[bid],
                    "idle": self.per_bot_idle[bid],
                }
                for bid in range(self.num_bots)
            },
            "order_completion_rounds": self.order_completion_rounds,
            "avg_delivery_size": (
                statistics.mean(self.delivery_sizes)
                if self.delivery_sizes
                else 0.0
            ),
            "blocked_move_pct": (
                self.stuck_rounds / max(1, self.moves) * 100
            ),
        }
