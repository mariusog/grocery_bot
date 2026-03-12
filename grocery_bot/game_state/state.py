"""GameState — persistent map caches, cross-round tracking."""

from typing import Any

from grocery_bot.constants import CORRIDOR_HEIGHT_THRESHOLD
from grocery_bot.game_state.distance import DistanceMixin
from grocery_bot.game_state.dropoff import DropoffMixin
from grocery_bot.game_state.hungarian import AssignmentMixin
from grocery_bot.game_state.path_cache import PathCacheMixin
from grocery_bot.game_state.route_tables import RouteTableMixin
from grocery_bot.game_state.tsp import TspMixin
from grocery_bot.pathfinding import find_adjacent_positions


class GameState(
    DistanceMixin,
    RouteTableMixin,
    TspMixin,
    AssignmentMixin,
    DropoffMixin,
    PathCacheMixin,
):
    """Encapsulates all mutable game state and caches for a single game."""

    def __init__(self) -> None:
        # Static map data
        self.blocked_static: set[tuple[int, int]] = set()
        self.dist_cache: dict[tuple[int, int], dict[tuple[int, int], int]] = {}
        self.adj_cache: dict[tuple[int, int], list[tuple[int, int]]] = {}
        self.grid_width: int = 0
        self.grid_height: int = 0
        self.corridor_y: list[int] = []
        self.idle_spots: list[tuple[int, int]] = []

        # Pickup tracking
        self.last_pickup: dict[int, tuple[str, int]] = {}
        self.pickup_fail_count: dict[str, int] = {}
        self.blacklisted_items: set[str] = set()
        self.blacklist_round: dict[str, int] = {}

        # Desync detection
        self.last_expected_pos: dict[int, tuple[int, int]] = {}
        self.last_round_processed: int = -1

        # Precomputed route tables
        self.best_pickup: dict[str, tuple[tuple[int, int], tuple[int, int], float]] = {}
        self.best_pair_route: dict[tuple[str, str], list[tuple[str, tuple[int, int]]]] = {}
        self.best_triple_route: dict[tuple[str, str, str], list[tuple[str, tuple[int, int]]]] = {}

        # Active items remaining on shelves
        self.active_on_shelves: int = 0

        # Dropoff congestion (T30)
        self.drop_off_pos: tuple[int, int] | None = None
        self.dropoff_adjacents: list[tuple[int, int]] = []
        self.dropoff_approach_cells: list[tuple[int, int]] = []
        self.dropoff_approach_set: set[tuple[int, int]] = set()
        self.dropoff_wait_cells: list[tuple[int, int]] = []

        # Path caching (T17)
        self.bot_planned_paths: dict[int, tuple[tuple[int, int], list[tuple[int, int]], int]] = {}

        # Round tracking (T30)
        self._round_bot_positions: dict[int, tuple[int, int]] = {}
        self._round_bot_targets: dict[int, tuple[int, int] | None] = {}
        self._round_drop_off: tuple[int, int] | None = None

        # Coordination (T15)
        self.delivery_queue: list[int] = []
        self.bot_tasks: dict[int, dict[str, Any]] = {}
        self.last_active_order_id: str | None = None

        # Bot history (oscillation detection)
        self.bot_history: dict[int, Any] = {}
        self._history_gen: int = 0
        self.spawn_origin: tuple[int, int] | None = None
        self.spawn_dispersal_targets: dict[int, tuple[int, int]] | None = None

        # Future order knowledge (from recorded maps)
        self.future_orders: list[dict[str, Any]] = []
        self.future_orders_recorded: int = 0
        self.future_demand: dict[str, int] = {}
        self._demand_order_idx: int = -1

        # Oracle planner schedule cache
        self._oracle_schedule: Any = None
        self._oracle_last_order_idx: int = -1
        self._oracle_stuck_counts: dict[int, int] = {}
        self._oracle_last_pos: dict[int, tuple[int, int]] = {}

    def reset(self) -> None:
        """Reset all state for a new game."""
        self.blocked_static = set()
        self.dist_cache = {}
        self.adj_cache = {}
        self.grid_width = 0
        self.grid_height = 0
        self.corridor_y = []
        self.idle_spots = []
        self.last_pickup = {}
        self.pickup_fail_count = {}
        self.blacklisted_items = set()
        self.blacklist_round = {}
        self.last_expected_pos = {}
        self.last_round_processed = -1
        self.best_pickup = {}
        self.best_pair_route = {}
        self.best_triple_route = {}
        self.active_on_shelves = 0
        self.drop_off_pos = None
        self.dropoff_adjacents = []
        self.dropoff_approach_cells = []
        self.dropoff_approach_set = set()
        self.dropoff_wait_cells = []
        self.bot_planned_paths = {}
        self._round_bot_positions = {}
        self._round_bot_targets = {}
        self._round_drop_off = None
        self.delivery_queue = []
        self.bot_tasks = {}
        self.last_active_order_id = None
        self.bot_history = {}
        self._history_gen = 0
        self.spawn_origin = None
        self.spawn_dispersal_targets = None
        self.future_orders = []
        self.future_orders_recorded = 0
        self.future_demand = {}
        self._demand_order_idx = -1
        self._oracle_schedule = None
        self._oracle_last_order_idx = -1
        self._oracle_stuck_counts = {}
        self._oracle_last_pos = {}

    def init_static(self, state: dict[str, Any]) -> None:
        """Compute static blocked set and caches on round 0."""
        self.dist_cache = {}
        self.adj_cache = {}
        self._history_gen += 1

        walls = {tuple(w) for w in state["grid"]["walls"]}
        width: int = state["grid"]["width"]
        height: int = state["grid"]["height"]
        self.grid_width = width
        self.grid_height = height
        item_positions = {tuple(it["position"]) for it in state["items"]}

        blocked: set[tuple[int, int]] = set(walls)
        for x in range(-1, width + 1):
            blocked.add((x, -1))
            blocked.add((x, height))
        for y in range(-1, height + 1):
            blocked.add((-1, y))
            blocked.add((width, y))
        blocked |= item_positions
        self.blocked_static = blocked

        for it in state["items"]:
            ipos = tuple(it["position"])
            self.adj_cache[ipos] = find_adjacent_positions(ipos[0], ipos[1], self.blocked_static)

        self._compute_idle_spots(width, height, item_positions)

        if "drop_off" in state:
            drop_off = tuple(state["drop_off"])
            self.drop_off_pos = drop_off
            self._precompute_dropoff_zones(drop_off)
            self._precompute_route_tables(state["items"], drop_off)

    def set_future_orders(
        self, orders: list[dict[str, Any]], recorded_count: int | None = None
    ) -> None:
        """Store the full order list for demand forecasting."""
        self.future_orders = orders
        self.future_orders_recorded = recorded_count if recorded_count is not None else len(orders)
        self._demand_order_idx = -1

    def update_demand(self, active_order_idx: int, lookahead: int = 3) -> None:
        """Recompute item demand from the next few orders (active + lookahead).

        Only counts the next ``lookahead`` orders beyond the active one so the
        demand map is selective enough to distinguish valuable items from
        dead weight.  With all remaining orders, every item type has demand.
        """
        if not self.future_orders or active_order_idx == self._demand_order_idx:
            return
        demand: dict[str, int] = {}
        end = min(len(self.future_orders), active_order_idx + lookahead)
        for order in self.future_orders[active_order_idx:end]:
            for item_type in order.get("items_required", []):
                demand[item_type] = demand.get(item_type, 0) + 1
        self.future_demand = demand
        self._demand_order_idx = active_order_idx

    def item_future_demand(self, item_type: str) -> int:
        """Return how many times this item type appears in remaining orders."""
        return self.future_demand.get(item_type, 0)

    def _compute_idle_spots(
        self, width: int, height: int, item_positions: set[tuple[int, int]]
    ) -> None:
        """Precompute strategic idle positions along the middle corridor."""
        mid = height // 2
        corridor_rows = [mid]
        if height > CORRIDOR_HEIGHT_THRESHOLD:
            corridor_rows.append(mid - 1)
        self.corridor_y = [y for y in corridor_rows if 1 <= y < height - 1]

        shelf_xs: set[int] = {pos[0] for pos in item_positions}
        walkway_xs: set[int] = set()
        for sx in shelf_xs:
            for dx in [-1, 1]:
                ax = sx + dx
                if 0 < ax < width - 1 and ax not in shelf_xs:
                    walkway_xs.add(ax)

        self.idle_spots = []
        for cy in self.corridor_y:
            for wx in sorted(walkway_xs):
                pos = (wx, cy)
                if pos not in self.blocked_static:
                    self.idle_spots.append(pos)

        for cy in self.corridor_y:
            for dy in [-1, 1]:
                ny = cy + dy
                if ny < 1 or ny >= height - 1:
                    continue
                for wx in sorted(walkway_xs):
                    pos = (wx, ny)
                    if pos not in self.blocked_static:
                        self.idle_spots.append(pos)
