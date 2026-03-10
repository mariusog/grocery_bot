"""Shared base class providing type declarations for all GameSimulator mixins."""

from __future__ import annotations

from typing import Any


class SimulatorBase:
    """Declares all shared attributes so mypy resolves cross-mixin references.

    No __init__ here — GameSimulator.__init__ initialises everything.
    """

    # --- Map geometry ---
    width: int
    height: int
    walls: list[tuple[int, int]]
    shelf_positions: set[tuple[int, int]]

    # --- Game objects ---
    bots: list[dict[str, Any]]
    items_on_map: list[dict[str, Any]]
    orders: list[dict[str, Any]]
    drop_off_zones: list[list[int]]

    # --- Round / score state ---
    round: int
    score: int
    items_delivered: int
    orders_completed: int
    active_order_idx: int
    _next_item_id: int
