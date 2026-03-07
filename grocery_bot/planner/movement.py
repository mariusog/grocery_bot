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
    DROPOFF_CLEAR_RADIUS,
    MAX_INVENTORY,
    MEDIUM_TEAM_MIN,
)


class MovementMixin:
    """Mixin providing movement, BFS, and action emission methods."""

    def _trace_static_bfs_path(
        self,
        start: tuple[int, int],
        goal: tuple[int, int],
    ) -> list[tuple[int, int]]:
        """Return the deterministic static BFS path used by repeated next-step BFS."""
        if start == goal:
            return [start]

        max_steps = self.gs.dist_static(start, goal)
        if max_steps == float("inf"):
            return []

        path = [start]
        seen = {start}
        pos = start

        for _ in range(int(max_steps)):
            nxt = bfs(pos, goal, self.gs.blocked_static)
            if nxt is None or nxt in seen:
                return []
            path.append(nxt)
            if nxt == goal:
                return path
            seen.add(nxt)
            pos = nxt

        return []

    def _emit(self, bid: int, bx: int, by: int, action_dict: dict[str, Any]) -> None:
        """Record action with yield-redirect and swap-collision prevention."""
        if action_dict["action"].startswith("move_"):
            predicted = _predict_pos(bx, by, action_dict["action"])
            # Yield to higher-urgency bots
            if self._yield_to and predicted in self._yield_to:
                action_dict = self._find_yield_alternative(bid, bx, by, predicted)
                predicted = _predict_pos(bx, by, action_dict["action"])
            # Prevent swap collisions: if we'd move into a cell occupied by
            # another bot that is predicted to move into our cell, the live
            # server blocks BOTH bots.  Detect and redirect.
            if action_dict["action"].startswith("move_"):
                my_pos = (bx, by)
                for b in self.bots:
                    if b["id"] == bid:
                        continue
                    other_pos = tuple(b["position"])
                    if other_pos != predicted:
                        continue
                    other_pred = self.predicted.get(b["id"])
                    if other_pred == my_pos:
                        action_dict = self._find_yield_alternative(
                            bid, bx, by, predicted
                        )
                        break

        self.actions.append(action_dict)
        expected = _predict_pos(bx, by, action_dict["action"])
        self.predicted[bid] = expected
        self.gs.last_expected_pos[bid] = expected
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

        Phase 2 detects idle bots sitting on active bots' optimal paths
        and predicts they will yield (move perpendicular), so active bots'
        BFS can path through without detours.
        """
        if len(self.bots) <= 1:
            return

        # Phase 1: compute targets and initial predictions
        active_paths: list[list[tuple[int, int]]] = []

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
                path = self._trace_static_bfs_path(pos, target)
                if len(path) >= 2:
                    active_paths.append(path)
                    self.predicted[bid] = path[1]
                    continue

            # Default: stay in place
            self.predicted[bid] = pos

        # Phase 2: predict yields for idle bots blocking active bots' paths
        if not active_paths:
            return

        for b in self.bots:
            bid = b["id"]
            pos = tuple(b["position"])

            # Only idle bots yield (no active items, no assignment)
            if self.bot_has_active.get(bid, False):
                continue
            if bid in self.bot_assignments and self.bot_assignments[bid]:
                continue
            if self.gs.dist_static(pos, self.drop_off) <= DROPOFF_CLEAR_RADIUS:
                continue

            occupied: set[tuple[int, int]] = {
                tuple(other["position"])
                for other in self.bots
                if other["id"] != bid
            }
            occupied |= {
                self.predicted.get(other["id"], tuple(other["position"]))
                for other in self.bots
                if other["id"] != bid
            }

            for path in active_paths:
                if pos not in path[1:]:
                    continue

                idx = path.index(pos)
                prev = path[idx - 1]
                if idx + 1 < len(path):
                    nxt = path[idx + 1]
                    dx_t = nxt[0] - prev[0]
                    dy_t = nxt[1] - prev[1]
                else:
                    dx_t = pos[0] - prev[0]
                    dy_t = pos[1] - prev[1]

                if abs(dx_t) >= abs(dy_t):
                    perp = [(0, -1), (0, 1), (-1, 0), (1, 0)]
                else:
                    perp = [(-1, 0), (1, 0), (0, -1), (0, 1)]

                path_cells = set(path)
                for dx, dy in perp:
                    yp = (pos[0] + dx, pos[1] + dy)
                    if yp in self.gs.blocked_static or yp in occupied:
                        continue
                    if yp in path_cells:
                        continue
                    self.predicted[bid] = yp
                    break
                break

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

        preferred = self.predicted.get(bid)
        current_dist = self.gs.dist_static(pos, target)
        if (
            preferred is not None
            and preferred != pos
            and preferred not in blocked
            and current_dist < float("inf")
            and self.gs.dist_static(preferred, target) == current_dist - 1
            and not self._would_oscillate(bid, preferred)
        ):
            return preferred

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
