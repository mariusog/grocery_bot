"""Idle positioning and dropoff clearing for RoundPlanner."""

from typing import Optional

from grocery_bot.pathfinding import DIRECTIONS, direction_to
from grocery_bot.constants import (
    BOT_HISTORY_MAXLEN,
    DROPOFF_CLEAR_RADIUS,
    IDLE_BOT_PROXIMITY_FACTOR,
    IDLE_BOT_PROXIMITY_RADIUS,
    IDLE_CORRIDOR_PENALTY,
    IDLE_DROPOFF_PENALTY_FACTOR,
    IDLE_DROPOFF_PENALTY_RADIUS,
    IDLE_STAY_IMPROVEMENT_THRESHOLD,
    IDLE_TARGET_DISTANCE_WEIGHT,
    PREDICTION_TEAM_MIN,
    SMALL_TEAM_MAX,
)


class IdleMixin:
    """Mixin providing idle bot positioning and dropoff area clearing."""

    def _try_clear_dropoff(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        blocked: set[tuple[int, int]],
    ) -> bool:
        if len(self.bots) <= 1:
            return False

        # T33: On large teams, use T30 congestion avoidance to route idle bots
        # away from the dropoff zone, giving deliverers more space.
        if len(self.bots) >= PREDICTION_TEAM_MIN:
            bot_positions = [tuple(b["position"]) for b in self.bots]
            if self.gs.is_dropoff_congested(self.drop_off, bot_positions):
                avoidance = self.gs.get_avoidance_target(pos, self.drop_off)
                if avoidance and avoidance != pos:
                    return self._emit_move(bid, bx, by, pos, avoidance, blocked)

        dist_to_drop = self.gs.dist_static(pos, self.drop_off)
        if dist_to_drop > DROPOFF_CLEAR_RADIUS:
            return False
        best_away: Optional[tuple[int, int]] = None
        best_dist = dist_to_drop
        for dx, dy in DIRECTIONS:
            npos = (bx + dx, by + dy)
            if npos in blocked:
                continue
            nd = self.gs.dist_static(npos, self.drop_off)
            if nd > best_dist:
                best_dist = nd
                best_away = npos
        if best_away:
            self._emit(
                bid,
                bx,
                by,
                {
                    "bot": bid,
                    "action": direction_to(bx, by, best_away[0], best_away[1]),
                },
            )
            return True
        return False

    def _try_idle_positioning(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        blocked: set[tuple[int, int]],
    ) -> bool:
        """Corridor-aware idle positioning with crowd avoidance.

        For large teams, idle bots spread across precomputed walkable
        aisle-entrance positions (idle spots on corridor rows) so they are
        ready when the next order activates. Uses predicted positions for
        active bots for better crowd avoidance, and biases toward staying
        still when already at an idle spot to reduce oscillation.
        """
        if len(self.bots) <= 1:
            return False

        # For large teams (8+), use predicted positions for active bots
        # (assigned or delivering) to better anticipate where they'll be.
        # For smaller teams, stick with current positions (predictions
        # can hurt when there are few bots and corridors are narrow).
        use_predictions = len(self.bots) >= PREDICTION_TEAM_MIN
        other_bot_positions: list[tuple[int, int]] = []
        for b in self.bots:
            if b["id"] == bid:
                continue
            if use_predictions:
                ob_id = b["id"]
                has_task = (
                    ob_id in self.bot_assignments and self.bot_assignments[ob_id]
                ) or self.bot_has_active.get(ob_id, False)
                if has_task:
                    other_bot_positions.append(
                        self.predicted.get(ob_id, tuple(b["position"]))
                    )
                else:
                    other_bot_positions.append(tuple(b["position"]))
            else:
                other_bot_positions.append(tuple(b["position"]))

        # Check if already at a precomputed idle spot (well-positioned)
        idle_spots = getattr(self.gs, "idle_spots", None)
        idle_set = set(idle_spots) if idle_spots else set()
        at_idle_spot = pos in idle_set

        # Detect stale idle: bot has been at the same position for too long
        is_large_team = len(self.bots) >= PREDICTION_TEAM_MIN
        is_stale = False
        if is_large_team:
            history = self.gs.bot_history.get(bid)
            if history and len(history) >= BOT_HISTORY_MAXLEN:
                if all(h == pos for h in history):
                    is_stale = True

        # Corridor rows to penalize for large teams
        corridor_ys = set(getattr(self.gs, "corridor_y", []))

        # Target: use idle_spots for unique spread targeting on Expert
        # (10 bots), fall back to shelf-column targeting for smaller teams.
        # For large teams, prefer off-corridor spots (not in corridor_y)
        # to avoid blocking active bots traversing the main corridor.
        item_target: Optional[tuple[int, int]] = None
        if idle_spots and is_large_team:
            # Large teams: assign each bot a unique idle spot for spread,
            # preferring off-corridor spots to keep corridors clear.
            off_corridor = [s for s in idle_spots if s[1] not in corridor_ys]
            on_corridor = [s for s in idle_spots if s[1] in corridor_ys]
            # Prefer off-corridor; fall back to on-corridor if not enough
            preferred = off_corridor + on_corridor
            n_bots = len(self.bots)
            bot_ids = sorted(b["id"] for b in self.bots)
            rank = bot_ids.index(bid)
            spot_idx = (rank * len(preferred)) // n_bots
            item_target = preferred[spot_idx]

        if item_target is None and len(self.bots) >= SMALL_TEAM_MAX and self.items:
            # Smaller teams or fallback: original shelf-column targeting
            item_positions = [tuple(it["position"]) for it in self.items]
            if item_positions:
                xs = sorted(set(p[0] for p in item_positions))
                if xs:
                    zone_idx = bid % len(xs)
                    target_x = xs[zone_idx]
                    col_ys = [p[1] for p in item_positions if p[0] == target_x]
                    if col_ys:
                        target_y = col_ys[len(col_ys) // 2]
                        item_target = (target_x, target_y)

        def _score(p: tuple[int, int]) -> float:
            """Lower is better."""
            s = 0.0
            # Penalize being near dropoff
            drop_dist = self.gs.dist_static(p, self.drop_off)
            if drop_dist <= IDLE_DROPOFF_PENALTY_RADIUS:
                s += (
                    IDLE_DROPOFF_PENALTY_RADIUS + 1 - drop_dist
                ) * IDLE_DROPOFF_PENALTY_FACTOR
            # Penalize being near other bots
            for ob_pos in other_bot_positions:
                ob_dist = abs(p[0] - ob_pos[0]) + abs(p[1] - ob_pos[1])
                if ob_dist <= IDLE_BOT_PROXIMITY_RADIUS:
                    s += (
                        IDLE_BOT_PROXIMITY_RADIUS + 1 - ob_dist
                    ) * IDLE_BOT_PROXIMITY_FACTOR
            # Penalize corridor rows on large teams (keep corridors clear)
            if is_large_team and corridor_ys and p[1] in corridor_ys:
                s += IDLE_CORRIDOR_PENALTY
            # Reward being near target
            if item_target:
                item_dist = abs(p[0] - item_target[0]) + abs(p[1] - item_target[1])
                s += item_dist * IDLE_TARGET_DISTANCE_WEIGHT
            return s

        stay_score = _score(pos)

        best: Optional[tuple[int, int]] = None
        best_score = stay_score
        for dx, dy in DIRECTIONS:
            npos = (bx + dx, by + dy)
            if npos in blocked:
                continue
            # Skip moves that would create A-B-A oscillation —
            # idle bots should stay put rather than bounce.
            if self._would_oscillate(bid, npos):
                continue
            s = _score(npos)
            if s < best_score:
                best_score = s
                best = npos

        if best:
            # When already at an idle spot, bias toward staying still:
            # only move if improvement is significant (>= 0.5 threshold).
            # This reduces oscillation from marginal score differences
            # when the bot is already well-positioned.
            # However, if the bot is stale (same position for IDLE_STALE_ROUNDS),
            # always move to prevent long-term corridor blocking.
            if (
                at_idle_spot
                and not is_stale
                and (stay_score - best_score) < IDLE_STAY_IMPROVEMENT_THRESHOLD
            ):
                return False
            self._emit(
                bid,
                bx,
                by,
                {"bot": bid, "action": direction_to(bx, by, best[0], best[1])},
            )
            return True
        return False
