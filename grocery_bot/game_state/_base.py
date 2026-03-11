"""Shared base class providing type declarations for all GameState mixins."""

from __future__ import annotations

from typing import Any


class GameStateBase:
    """Declares all shared attributes so mypy resolves cross-mixin references.

    No __init__ here — GameState.__init__ initialises everything.
    This class exists solely to carry type annotations.
    """

    # --- BFS / distance cache ---
    blocked_static: set[tuple[int, int]]
    dist_cache: dict[tuple[int, int], dict[tuple[int, int], int]]
    adj_cache: dict[tuple[int, int], list[tuple[int, int]]]

    # --- Map geometry ---
    grid_width: int
    grid_height: int
    corridor_y: list[int]
    idle_spots: list[tuple[int, int]]

    # --- Route tables ---
    best_pickup: dict[str, tuple[tuple[int, int], tuple[int, int], float]]
    best_pair_route: dict[tuple[str, str], list[tuple[str, tuple[int, int]]]]
    best_triple_route: dict[tuple[str, str, str], list[tuple[str, tuple[int, int]]]]

    # --- Active item tracking ---
    active_on_shelves: int

    # --- Dropoff congestion ---
    drop_off_pos: tuple[int, int] | None
    dropoff_adjacents: list[tuple[int, int]]
    dropoff_approach_cells: list[tuple[int, int]]
    dropoff_approach_set: set[tuple[int, int]]
    dropoff_wait_cells: list[tuple[int, int]]

    # --- Path cache ---
    bot_planned_paths: dict[int, tuple[tuple[int, int], list[tuple[int, int]], int]]

    # --- Round tracking ---
    _round_bot_positions: dict[int, tuple[int, int]]
    _round_bot_targets: dict[int, tuple[int, int] | None]
    _round_drop_off: tuple[int, int] | None

    # --- Coordination ---
    delivery_queue: list[int]
    bot_tasks: dict[int, dict[str, Any]]
    last_active_order_id: str | None

    # --- Bot history ---
    bot_history: dict[int, Any]
    _history_gen: int
    spawn_origin: tuple[int, int] | None
    spawn_dispersal_targets: dict[int, tuple[int, int]] | None

    # --- Pickup tracking ---
    last_pickup: dict[int, tuple[str, int]]
    pickup_fail_count: dict[str, int]
    blacklisted_items: set[str]
    blacklist_round: dict[str, int]
    last_expected_pos: dict[int, tuple[int, int]]
    last_round_processed: int

    # --- Cross-mixin method stubs (implemented in DistanceMixin) ---

    def dist_static(self, a: tuple[int, int], b: tuple[int, int]) -> float:
        """BFS distance between two cells. Provided by DistanceMixin."""
        raise NotImplementedError

    def find_best_item_target(
        self, pos: tuple[int, int], item: dict[str, Any]
    ) -> tuple[tuple[int, int] | None, float]:
        """Closest reachable adjacent cell for an item. Provided by DistanceMixin."""
        raise NotImplementedError
