"""Team-size-dependent configuration for bot behavior.

Instead of scattering ``if len(self.bots) >= N`` checks everywhere, each
team-size tier gets a frozen config object with all the parameters the
planner needs.  Created once per game via ``get_team_config(num_bots)``.
"""

from dataclasses import dataclass

from grocery_bot.constants import (
    BLOCKING_RADIUS_EXPERT,
    BLOCKING_RADIUS_HUGE_TEAM,
    BLOCKING_RADIUS_LARGE_TEAM,
    IDLE_PREVIEW_STAGE_WEIGHT_5BOT,
    IDLE_PREVIEW_STAGE_WEIGHT_10BOT,
    IDLE_TARGET_DISTANCE_WEIGHT,
    MAX_CONCURRENT_DELIVERERS,
    MAX_INVENTORY,
    MAX_NONACTIVE_DELIVERERS,
    MIN_INV_FOR_NONACTIVE_DELIVERY,
)


@dataclass(frozen=True)
class TeamConfig:
    """All team-size-dependent parameters in a single immutable object."""

    num_bots: int

    # --- Blocking / collision ---
    blocking_radius: float

    # --- Delivery control ---
    use_coordination: bool
    max_concurrent_deliverers: int
    max_nonactive_deliverers: int
    min_inv_nonactive_idle: int

    # --- Preview / speculative ---
    enable_speculative: bool
    enable_spec_assignment: bool

    # --- Assignment ---
    use_best_pickup: bool
    use_dropoff_weight: bool

    # --- Idle positioning ---
    preview_stage_weight: float
    target_attraction_weight: float
    use_idle_spots: bool
    use_corridor_penalty: bool
    use_predictions: bool
    use_temporal_bfs: bool

    # --- Coordination ---
    extra_preview_roles: bool

    # --- Simple gates ---
    multi_bot: bool

    # --- Methods for runtime-dependent values ---

    def max_walkers(self, active_on_shelves: int) -> int:
        """Preview walkers cap (depends on runtime active count)."""
        if self.num_bots >= 8:
            return max(2, self.num_bots - active_on_shelves - 2)
        return max(2, self.num_bots // 2)

    def nonactive_clear_min_inv(self, has_assignment: bool) -> int:
        """Min inventory for non-active clearing."""
        if self.num_bots >= 8:
            return 1 if has_assignment else 2
        if self.num_bots <= 3:
            return MIN_INV_FOR_NONACTIVE_DELIVERY
        return MAX_INVENTORY  # medium teams (4-7): require full inventory to clear

    def preview_prepick_force(
        self,
        has_assignment: bool,
        has_active: bool,
        active_on_shelves: int,
    ) -> bool:
        """Whether to force-use slots for preview prepick."""
        if self.num_bots >= 8:
            return not has_assignment and not has_active
        if self.num_bots >= 6:
            return active_on_shelves == 0
        if self.num_bots >= 3:
            return active_on_shelves <= 1
        return False

    def rush_max_deliverers(self) -> int:
        """Max deliverers during rush-deliver step."""
        return max(2, self.num_bots // 4)

    def max_spec_pickers(self) -> int:
        """Max speculative pickers per round."""
        return max(self.num_bots // 2, 4)

    def num_zones(self, n_assignable: int) -> int:
        """Number of assignment zones."""
        if self.num_bots >= 8:
            return max(2, n_assignable // 3)
        if self.num_bots >= 5:
            return max(1, n_assignable // 2)
        return 1


def get_team_config(num_bots: int) -> TeamConfig:
    """Select the right TeamConfig for a given team size."""
    # Blocking radius
    if num_bots < 5:
        blocking_radius = float("inf")
    elif 8 <= num_bots < 15:
        blocking_radius = float(BLOCKING_RADIUS_EXPERT)
    elif num_bots >= 15:
        blocking_radius = float(BLOCKING_RADIUS_HUGE_TEAM)
    else:
        blocking_radius = float(BLOCKING_RADIUS_LARGE_TEAM)

    # Delivery concurrency
    if num_bots >= 8:
        max_concurrent = max(2, num_bots // 4)
        max_nonactive = max(MAX_NONACTIVE_DELIVERERS, num_bots // 3)
    elif num_bots >= 5:
        max_concurrent = 2
        max_nonactive = MAX_NONACTIVE_DELIVERERS
    else:
        max_concurrent = MAX_CONCURRENT_DELIVERERS
        max_nonactive = MAX_NONACTIVE_DELIVERERS

    # Preview stage weight
    if num_bots >= 10:
        preview_stage = IDLE_PREVIEW_STAGE_WEIGHT_10BOT
    elif num_bots >= 5:
        preview_stage = IDLE_PREVIEW_STAGE_WEIGHT_5BOT
    else:
        preview_stage = 0.0

    return TeamConfig(
        num_bots=num_bots,
        blocking_radius=blocking_radius,
        use_coordination=num_bots >= 4,
        max_concurrent_deliverers=max_concurrent,
        max_nonactive_deliverers=max_nonactive,
        min_inv_nonactive_idle=(
            1 if num_bots >= 8 else MIN_INV_FOR_NONACTIVE_DELIVERY
        ),
        enable_speculative=num_bots >= 5,
        enable_spec_assignment=num_bots >= 8,
        use_best_pickup=num_bots < 8,
        use_dropoff_weight=num_bots > 3,
        preview_stage_weight=preview_stage,
        target_attraction_weight=(
            0.0 if num_bots >= 10 else IDLE_TARGET_DISTANCE_WEIGHT
        ),
        use_idle_spots=num_bots >= 8,
        use_corridor_penalty=num_bots >= 8,
        use_predictions=num_bots >= 8,
        use_temporal_bfs=num_bots > 1,
        extra_preview_roles=num_bots >= 8,
        multi_bot=num_bots > 1,
    )
