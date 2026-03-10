"""Shared base class providing type declarations for all planner mixins.

This module exists solely to give mypy visibility into the attributes and
methods that RoundPlanner initialises and that are shared across mixins.
No logic lives here — only type annotations and abstract-like stubs.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from grocery_bot.team_config import TeamConfig


class PlannerBase:
    """Declares all shared attributes and cross-mixin method signatures.

    RoundPlanner.__init__ and the various mixin methods own the actual
    implementation.  This class carries only the type annotations so that
    every mixin that inherits from PlannerBase can reference these names
    without an [attr-defined] error.
    """

    # ------------------------------------------------------------------ #
    # Core game-state reference
    # ------------------------------------------------------------------ #
    gs: Any  # GameState instance

    # ------------------------------------------------------------------ #
    # Team config
    # ------------------------------------------------------------------ #
    cfg: TeamConfig

    # ------------------------------------------------------------------ #
    # Round-level game data (set in __init__)
    # ------------------------------------------------------------------ #
    full_state: dict[str, Any]
    bots: list[dict[str, Any]]
    items: list[dict[str, Any]]
    orders: list[dict[str, Any]]
    drop_off: tuple[int, int]
    drop_off_zones: list[tuple[int, int]]
    current_round: int
    rounds_left: int
    endgame: bool

    # ------------------------------------------------------------------ #
    # Per-round derived structures
    # ------------------------------------------------------------------ #
    bots_by_id: dict[int, dict[str, Any]]
    items_at_pos: dict[tuple[int, int], list[dict[str, Any]]]
    items_by_type: dict[str, list[dict[str, Any]]]

    # ------------------------------------------------------------------ #
    # Per-round mutable state (set in __init__)
    # ------------------------------------------------------------------ #
    actions: list[dict[str, Any]]
    predicted: dict[int, tuple[int, int]]
    claimed: set[str]
    _yield_to: set[tuple[int, int]]
    _nonactive_delivering: int
    _preview_walkers: int
    _speculative_pickers: int
    _spec_types_claimed: set[str]
    spec_assignments: dict[int, dict[str, Any]]

    # ------------------------------------------------------------------ #
    # Order references (set in plan())
    # ------------------------------------------------------------------ #
    active: dict[str, Any] | None
    preview: dict[str, Any] | None

    # ------------------------------------------------------------------ #
    # Computed needs (set in _compute_needs())
    # ------------------------------------------------------------------ #
    active_needed: dict[str, int]
    net_active: dict[str, int]
    net_preview: dict[str, int]
    bot_carried_active: dict[int, dict[str, int]]
    bot_has_active: dict[int, bool]
    active_on_shelves: int
    active_types: set[str]
    order_nearly_complete: bool
    max_claim: int
    num_item_types: int
    preview_bot_id: int | None
    preview_bot_ids: set[int]
    wave_mode: bool
    wave_on_shelves: int
    batch_b_bots: set[int]

    # ------------------------------------------------------------------ #
    # Bot assignments (set in _compute_bot_assignments())
    # ------------------------------------------------------------------ #
    bot_assignments: dict[int, list[dict[str, Any]]]

    # ------------------------------------------------------------------ #
    # Roles / coordination (set in plan())
    # ------------------------------------------------------------------ #
    bot_roles: dict[int, str]
    _use_coordination: bool
    _decided: set[int]

    # ------------------------------------------------------------------ #
    # Cross-mixin method stubs (implemented in the respective mixin)
    # These stubs let mypy resolve cross-references without errors.
    # raise NotImplementedError ensures they are never called on PlannerBase
    # directly — only on the concrete RoundPlanner class.
    # ------------------------------------------------------------------ #

    # -- RoundPlanner (round_planner.py) --
    def _nearest_dropoff(self, pos: tuple[int, int]) -> tuple[int, int]:
        raise NotImplementedError

    def _is_at_any_dropoff(self, pos: tuple[int, int]) -> bool:
        raise NotImplementedError

    def _spare_slots(self, inv: list[str], bid: int = -1) -> int:
        raise NotImplementedError

    def _claim(self, item: dict[str, Any], needed_dict: dict[str, int]) -> None:
        raise NotImplementedError

    def _iter_needed_items(self, needed: dict[str, int]) -> Iterator[tuple[dict[str, Any], bool]]:
        raise NotImplementedError
        yield  # make mypy treat this as a generator

    def _find_adjacent_needed(
        self,
        bx: int,
        by: int,
        needed: dict[str, int],
        prefer_cascade: bool = False,
    ) -> dict[str, Any] | None:
        raise NotImplementedError

    def _is_available(self, item: dict[str, Any]) -> bool:
        raise NotImplementedError

    @staticmethod
    def _pickup(bid: int, item: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    # -- MovementMixin (movement.py) --
    def _emit(self, bid: int, bx: int, by: int, action_dict: dict[str, Any]) -> None:
        raise NotImplementedError

    def _emit_move(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        target: tuple[int, int],
        blocked: set[tuple[int, int]],
    ) -> bool:
        raise NotImplementedError

    def _emit_move_or_wait(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        target: tuple[int, int],
        blocked: set[tuple[int, int]],
    ) -> None:
        raise NotImplementedError

    def _would_oscillate(self, bid: int, next_pos: tuple[int, int]) -> bool:
        raise NotImplementedError

    def _should_head_to_dropoff(self, bot: dict[str, Any]) -> bool:
        raise NotImplementedError

    def _get_delivery_target(
        self,
        bid: int,
        pos: tuple[int, int],
    ) -> tuple[tuple[int, int], bool]:
        raise NotImplementedError

    # -- DeliveryMixin (delivery.py) --
    def _emit_delivery_move_or_wait(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        blocked: set[tuple[int, int]],
    ) -> None:
        raise NotImplementedError

    def _should_deliver_early(self, pos: tuple[int, int], inv: list[str]) -> bool:
        raise NotImplementedError

    def _estimate_rounds_to_complete(self, pos: tuple[int, int], inv: list[str]) -> float:
        raise NotImplementedError

    def _try_maximize_items(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        inv: list[str],
        blocked: set[tuple[int, int]],
    ) -> bool:
        raise NotImplementedError

    # -- AssignmentMixin (assignment.py) --
    def _is_delivering(self, bot: dict[str, Any]) -> bool:
        raise NotImplementedError

    def _bot_delivery_completes_order(self, bot: dict[str, Any]) -> bool:
        raise NotImplementedError

    def _identify_batch_b(self) -> None:
        raise NotImplementedError

    # -- PickupMixin (pickup.py) --
    def _try_active_pickup(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        inv: list[str],
        blocked: set[tuple[int, int]],
    ) -> bool:
        raise NotImplementedError

    # -- PreviewMixin (preview.py) --
    def _try_preview_prepick(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        inv: list[str],
        blocked: set[tuple[int, int]],
        force_slots: bool = False,
        force_walkers: bool = False,
    ) -> bool:
        raise NotImplementedError

    def _find_detour_item(
        self,
        pos: tuple[int, int],
        needed: dict[str, int],
        max_detour: int = 0,
        prefer_cascade: bool = False,
    ) -> tuple[dict[str, Any] | None, tuple[int, int] | None]:
        raise NotImplementedError

    def _find_nearest_active_item_pos(self, pos: tuple[int, int]) -> tuple[int, int] | None:
        raise NotImplementedError

    # -- IdleMixin (idle.py) --
    def _is_stuck_oscillating(self, bid: int) -> bool:
        raise NotImplementedError

    def _try_clear_dropoff(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        blocked: set[tuple[int, int]],
    ) -> bool:
        raise NotImplementedError

    def _try_idle_positioning(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        blocked: set[tuple[int, int]],
    ) -> bool:
        raise NotImplementedError
