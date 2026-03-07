"""Movement, collision avoidance, and action emission for RoundPlanner."""

from typing import Any, Optional

from grocery_bot.pathfinding import (
    DIRECTIONS,
    bfs,
    bfs_temporal,
    direction_to,
    _predict_pos,
)
from grocery_bot.constants import (
    BLOCKING_RADIUS_LARGE_TEAM,
    MAX_INVENTORY,
    MEDIUM_TEAM_MIN,
)


class MovementMixin:
    """Mixin providing movement, BFS, and action emission methods."""

    def _emit(self, bid: int, bx: int, by: int, action_dict: dict[str, Any]) -> None:
        """Record action with yield-redirect for higher-urgency bots."""
        if self._yield_to and action_dict["action"].startswith("move_"):
            predicted = _predict_pos(bx, by, action_dict["action"])
            if predicted in self._yield_to:
                action_dict = self._find_yield_alternative(bid, bx, by, predicted)

        self.actions.append(action_dict)
        self.predicted[bid] = _predict_pos(bx, by, action_dict["action"])
        if hasattr(self, "_decided"):
            self._decided.add(bid)

        if action_dict["action"] == "pick_up":
            self.gs.last_pickup[bid] = (
                action_dict["item_id"],
                len(self.bots_by_id[bid]["inventory"]),
            )

    def _find_yield_alternative(
        self,
        bid: int,
        bx: int,
        by: int,
        blocked_target: tuple[int, int],
    ) -> dict[str, Any]:
        occupied: set[tuple[int, int]] = {
            self.predicted.get(b["id"], tuple(b["position"]))
            for b in self.bots
            if b["id"] != bid
        }
        # Prefer non-oscillating alternatives, but fall back to any unblocked
        fallback: Optional[dict[str, Any]] = None
        for dx, dy in DIRECTIONS:
            alt = (bx + dx, by + dy)
            if alt == blocked_target or alt in self.gs.blocked_static:
                continue
            if alt in occupied:
                continue
            action = {"bot": bid, "action": direction_to(bx, by, alt[0], alt[1])}
            if not self._would_oscillate(bid, alt):
                return action
            if fallback is None:
                fallback = action
        return fallback if fallback is not None else {"bot": bid, "action": "wait"}

    def _pre_predict(self) -> None:
        """Estimate where each bot will move BEFORE detailed planning.

        Gives temporal BFS better information about undecided bots.
        Predictions are stored in self.predicted and get overwritten
        by actual decisions during _decide_bot.
        """
        if len(self.bots) <= 1:
            return

        for b in self.bots:
            bid: int = b["id"]
            pos: tuple[int, int] = tuple(b["position"])
            has_active: bool = self.bot_has_active.get(bid, False)
            inv: list[str] = b["inventory"]

            target: Optional[tuple[int, int]] = None

            # Delivering bots with full inventory or no items left to pick
            if has_active and (
                len(inv) >= MAX_INVENTORY or self.active_on_shelves == 0
            ):
                target = self.drop_off

            # Bots at dropoff with active items will drop off (stay put)
            elif pos == self.drop_off and has_active:
                self.predicted[bid] = pos
                continue

            # Bots with assigned items move toward first assigned item
            elif bid in self.bot_assignments and self.bot_assignments[bid]:
                first_item = self.bot_assignments[bid][0]
                cell, _ = self.gs.find_best_item_target(pos, first_item)
                if cell:
                    target = cell

            if target and target != pos:
                nxt = bfs(pos, target, self.gs.blocked_static)
                if nxt:
                    self.predicted[bid] = nxt
                    continue

            # Default: stay in place
            self.predicted[bid] = pos

    def _build_moving_obstacles(
        self, bid: int
    ) -> list[tuple[tuple[int, int], tuple[int, int]]]:
        """Build moving obstacle list for temporal BFS (other bots only)."""
        obstacles: list[tuple[tuple[int, int], tuple[int, int]]] = []
        for b in self.bots:
            if b["id"] == bid:
                continue
            cur: tuple[int, int] = tuple(b["position"])
            pred: tuple[int, int] = self.predicted.get(b["id"], cur)
            obstacles.append((cur, pred))
        return obstacles

    def _bfs_smart(
        self,
        bid: int,
        pos: tuple[int, int],
        target: tuple[int, int],
        blocked: set[tuple[int, int]],
    ) -> Optional[tuple[int, int]]:
        """Use cached full-path, then temporal BFS, then standard BFS.

        T17: First tries the cached deterministic path to avoid flip-flopping.
        Falls back to temporal / standard BFS when the cached step is blocked,
        and stores the resulting path for future rounds.

        Includes oscillation detection: if the proposed next step would
        return the bot to its position from 2 rounds ago (A-B-A bounce),
        invalidate the cached path and recompute via live BFS.
        """
        # T17: Try cached path first (avoids oscillation from BFS ties).
        use_cache = True
        if use_cache:
            dynamic_blocked = blocked - self.gs.blocked_static
            current_round = getattr(self, "current_round", 0)
            had_cache = bid in self.gs.bot_planned_paths
            cached = self.gs.get_cached_next_step(
                bid, pos, target, dynamic_blocked, current_round
            )
            if cached is not None and cached not in blocked:
                if not self._would_oscillate(bid, cached):
                    return cached
                # Cache leads to oscillation — invalidate and recompute
                self.gs.bot_planned_paths.pop(bid, None)
                had_cache = False

        # Cached path unavailable or blocked — fall back to live BFS
        result: Optional[tuple[int, int]] = None
        if len(self.bots) > 1:
            obstacles = self._build_moving_obstacles(bid)
            result = bfs_temporal(pos, target, self.gs.blocked_static, obstacles)
            if result and result in blocked:
                result = None
        if result is None:
            result = bfs(pos, target, blocked)
            if result and result in blocked:
                result = None

        # If live BFS also oscillates, try static-only BFS (ignoring other
        # bots) to get a stable, non-oscillating path.  If that also
        # oscillates, keep the original result — oscillating is better
        # than waiting indefinitely.
        if result is not None and self._would_oscillate(bid, result):
            static_result = bfs(pos, target, self.gs.blocked_static)
            if (
                static_result
                and static_result not in self.gs.blocked_static
                and not self._would_oscillate(bid, static_result)
            ):
                result = static_result

        # T17: Store the full path when no cache exists yet, or when the
        # cache was invalidated (target changed, position mismatch, or
        # shorter path found).  Don't overwrite when the cache is merely
        # skipped due to temporary dynamic blocking.
        if use_cache and result is not None:
            if not had_cache or bid not in self.gs.bot_planned_paths:
                self.gs.store_path_for_step(
                    bid, pos, result, target, current_round
                )

        return result

    def _emit_move(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        target: tuple[int, int],
        blocked: set[tuple[int, int]],
    ) -> bool:
        """BFS to target and emit. Returns True if a move was emitted."""
        next_pos = self._bfs_smart(bid, pos, target, blocked)
        if next_pos:
            self._emit(
                bid,
                bx,
                by,
                {"bot": bid, "action": direction_to(bx, by, next_pos[0], next_pos[1])},
            )
            return True
        return False

    def _would_oscillate(self, bid: int, next_pos: tuple[int, int]) -> bool:
        """Check if moving to next_pos would create an A-B-A oscillation.

        Returns True when next_pos matches the position from 2 rounds ago,
        meaning the bot would bounce back to where it just came from.
        """
        history = self.gs.bot_history.get(bid)
        if not history or len(history) < 2:
            return False
        return next_pos == history[-2]

    def _emit_move_or_wait(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        target: tuple[int, int],
        blocked: set[tuple[int, int]],
    ) -> None:
        """Move toward target with unstick fallback.

        Oscillation detection is handled inside _bfs_smart, so this
        method just needs the unstick fallback for fully blocked cases.
        """
        next_pos = self._bfs_smart(bid, pos, target, blocked)

        if not next_pos:
            # Prefer non-oscillating neighbors, fall back to any unblocked
            fallback_pos: Optional[tuple[int, int]] = None
            for dx, dy in DIRECTIONS:
                npos = (bx + dx, by + dy)
                if npos not in blocked:
                    if not self._would_oscillate(bid, npos):
                        next_pos = npos
                        break
                    if fallback_pos is None:
                        fallback_pos = npos
            if not next_pos:
                next_pos = fallback_pos
        if next_pos:
            self._emit(
                bid,
                bx,
                by,
                {"bot": bid, "action": direction_to(bx, by, next_pos[0], next_pos[1])},
            )
        else:
            self._emit(bid, bx, by, {"bot": bid, "action": "wait"})

    def _build_blocked(self, bid: int) -> set[tuple[int, int]]:
        """Build blocked set for a specific bot (static + nearby other bots)."""
        pos: tuple[int, int] = tuple(self.bots_by_id[bid]["position"])
        max_dist: float = (
            BLOCKING_RADIUS_LARGE_TEAM
            if len(self.bots) >= MEDIUM_TEAM_MIN
            else float("inf")
        )
        other: set[tuple[int, int]] = set()
        for b in self.bots:
            if b["id"] == bid:
                continue
            bp: tuple[int, int] = self.predicted.get(b["id"], tuple(b["position"]))
            if (
                max_dist == float("inf")
                or (abs(bp[0] - pos[0]) + abs(bp[1] - pos[1])) <= max_dist
            ):
                other.add(bp)
        return self.gs.blocked_static | other
