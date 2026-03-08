"""GameSimulator — core simulation engine for testing bot performance."""

import random
import time
from collections import defaultdict

import bot

from grocery_bot.simulator.map_generator import generate_store_layout, generate_orders
from grocery_bot.simulator.diagnostics import DiagnosticTracker
from grocery_bot.simulator.presets import DIFFICULTY_PRESETS
from grocery_bot.simulator.physics import PhysicsMixin
from grocery_bot.simulator.sim_logging import (
    compute_timing_stats,
    log_round,
    save_local_log,
    # Re-export so existing `import game_simulator as gs_mod` keeps working
    _LOG_DIR,
    _MAX_LOCAL_LOGS,
    infer_difficulty_slug as _infer_difficulty_slug,
)


class GameSimulator(PhysicsMixin):
    """Simulates the grocery bot game locally."""

    def __init__(
        self,
        seed: int = 42,
        num_bots: int = 1,
        width: int = 12,
        height: int = 10,
        num_item_types: int = 4,
        items_per_order: tuple[int, int] = (3, 4),
        max_rounds: int = 300,
    ) -> None:
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
        self.drop_off_zones = [self.drop_off]
        self.spawn = [width - 2, height - 2]

        # Generate orders
        self.orders = generate_orders(self.rng, self.item_type_names, items_per_order)

        self._init_game_state()
        self._init_bots()
        self._init_items()

    def _init_game_state(self) -> None:
        """Reset round counters and score."""
        self.round = 0
        self.score = 0
        self.items_delivered = 0
        self.orders_completed = 0
        self.active_order_idx = 0

    def _init_bots(self) -> None:
        """Place bots at spawn."""
        self.bots = []
        for i in range(self.num_bots):
            self.bots.append({
                "id": i,
                "position": list(self.spawn),
                "inventory": [],
            })

    def _init_items(self) -> None:
        """Populate items on the map from shelf data."""
        self.items_on_map = []
        for i, (x, y, itype) in enumerate(self.item_shelves):
            self.items_on_map.append({
                "id": f"item_{i}",
                "type": itype,
                "position": [x, y],
            })
        self._next_item_id = len(self.item_shelves)

    def get_state(self) -> dict:
        """Build game state dict matching the server format."""
        orders = _build_visible_orders(
            self.orders, self.active_order_idx,
        )
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
            "drop_off_zones": [list(z) for z in self.drop_off_zones],
            "score": self.score,
            "active_order_index": self.active_order_idx,
            "total_orders": len(self.orders),
        }

    def is_over(self) -> bool:
        """Return True when the maximum round count has been reached."""
        return self.round >= self.max_rounds

    def run(
        self,
        verbose: bool = False,
        profile: bool = False,
        diagnose: bool = False,
        log: bool = False,
    ) -> dict:
        """Run full game, return results dict."""
        bot.reset_state()
        timings = defaultdict(list) if profile else None
        tracker = DiagnosticTracker(self) if diagnose else None
        log_rows: list[dict] | None = [] if log else None

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
                log_round(state, actions, log_rows)

            self.apply_actions(actions)

            if tracker:
                tracker.post_round(self, actions)

            if verbose and self.round % 50 == 0:
                _print_progress(self)

        result = self._build_result(timings, tracker, log_rows)
        if verbose:
            print(f"  Final: {result}")
        return result

    def _build_result(
        self,
        timings: defaultdict | None,
        tracker: DiagnosticTracker | None,
        log_rows: list[dict] | None,
    ) -> dict:
        """Assemble the final result dict after a run."""
        result = {
            "score": self.score,
            "items_delivered": self.items_delivered,
            "orders_completed": self.orders_completed,
            "rounds_used": self.round,
        }
        if timings:
            result["timings"] = compute_timing_stats(timings)
        if tracker:
            result["diagnostics"] = tracker.get_results()
        if log_rows is not None:
            diag = result.get("diagnostics")
            result["log_path"] = save_local_log(self, log_rows, diagnostics=diag)
        return result


def _build_visible_orders(orders: list[dict], active_idx: int) -> list[dict]:
    """Return the active and preview orders visible to the bot."""
    visible: list[dict] = []
    if active_idx < len(orders):
        visible.append({**orders[active_idx], "status": "active"})
    if active_idx + 1 < len(orders):
        visible.append({**orders[active_idx + 1], "status": "preview"})
    return visible


def _print_progress(sim: "GameSimulator") -> None:
    """Print a progress line during verbose runs."""
    print(
        f"  Round {sim.round}: score={sim.score}, "
        f"orders={sim.orders_completed}, "
        f"items={sim.items_delivered}"
    )
