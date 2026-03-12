"""Movement, collision avoidance, and action emission for RoundPlanner."""

from typing import Any

from grocery_bot.constants import (
    DROPOFF_CLEAR_RADIUS,
)
from grocery_bot.pathfinding import (
    DIRECTIONS,
    _predict_pos,
    bfs,
    bfs_temporal,
    direction_to,
)
from grocery_bot.planner._base import PlannerBase


class MovementMixin(PlannerBase):
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
                        action_dict = self._find_yield_alternative(bid, bx, by, predicted)
                        break
            # Prevent convergence: two decided bots targeting the same cell.
            # The server rejects one move, causing a desync.
            if action_dict["action"].startswith("move_"):
                predicted = _predict_pos(bx, by, action_dict["action"])
                decided = getattr(self, "_decided", set())
                for other_bid, other_pred in self.predicted.items():
                    if other_bid == bid or other_bid not in decided:
                        continue
                    if other_pred == predicted:
                        action_dict = self._find_yield_alternative(bid, bx, by, predicted)
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
        decided: set[int] = getattr(self, "_decided", set())
        occupied: set[tuple[int, int]] = set()
        for b in self.bots:
            if b["id"] == bid:
                continue
            if b["id"] < bid and b["id"] in decided:
                occupied.add(self.predicted.get(b["id"], tuple(b["position"])))
            else:
                occupied.add(tuple(b["position"]))
        # Prefer non-oscillating alternatives, but fall back to any unblocked
        fallback: dict[str, Any] | None = None
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
        if not self.cfg.multi_bot:
            return
        active_paths = self._pre_predict_phase1()
        if active_paths:
            self._pre_predict_phase2(active_paths)

    def _pre_predict_phase1(self) -> list[list[tuple[int, int]]]:
        """Phase 1: compute targets and store initial position predictions.

        Returns paths of active/delivering bots for use in phase 2.
        """
        active_paths: list[list[tuple[int, int]]] = []
        # During lane-based spawn dispersal, bots at spawn will disperse —
        # not follow assignments.  Skip predictions so they don't block exits.
        # Only for lane dispersal (single-dropoff maps like Expert).
        spawn: tuple[int, int] | None = None
        if (
            self.cfg.use_spawn_dispersal
            and getattr(self.gs, "spawn_lane_dispersal", False)
            and self.current_round < self.cfg.spawn_dispersal_max_rounds()
        ):
            spawn = (
                tuple(self.gs.spawn_origin)  # type: ignore[arg-type]
                if self.gs.spawn_origin is not None
                else None
            )
        for b in self.bots:
            bid: int = b["id"]
            pos: tuple[int, int] = tuple(b["position"])
            has_active: bool = self.bot_has_active.get(bid, False)
            target: tuple[int, int] | None = None

            if spawn and pos == spawn:
                self.predicted[bid] = pos
                continue

            if has_active and self._should_head_to_dropoff(b):
                target, _ = self._get_delivery_target(bid, pos)
            elif self._is_at_any_dropoff(pos) and has_active:
                self.predicted[bid] = pos
                continue
            elif self.bot_assignments.get(bid):
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

            self.predicted[bid] = pos
        return active_paths

    def _pre_predict_phase2(self, active_paths: list[list[tuple[int, int]]]) -> None:
        """Phase 2: predict yields for idle bots blocking active bots' paths.

        Idle bots on an active bot's path are predicted to step perpendicular,
        so active bots' BFS can path through without detours.
        """
        for b in self.bots:
            bid = b["id"]
            pos: tuple[int, int] = tuple(b["position"])

            if self.bot_has_active.get(bid, False) or self.bot_assignments.get(bid):
                continue
            occupied: set[tuple[int, int]] = {
                tuple(other["position"]) for other in self.bots if other["id"] != bid
            }
            occupied |= {
                self.predicted.get(other["id"], tuple(other["position"]))
                for other in self.bots
                if other["id"] != bid
            }

            nearest_do = self._nearest_dropoff(pos)
            if self.gs.dist_static(pos, nearest_do) <= DROPOFF_CLEAR_RADIUS:
                bot_positions = [tuple(other["position"]) for other in self.bots]
                if self.gs.is_dropoff_congested(nearest_do, bot_positions):
                    avoidance = self.gs.get_avoidance_target(pos, nearest_do)
                    if avoidance and avoidance != pos and avoidance not in occupied:
                        self.predicted[bid] = avoidance
                continue

            for path in active_paths:
                if pos not in path[1:]:
                    continue
                idx = path.index(pos)
                prev = path[idx - 1]
                if idx + 1 < len(path):
                    nxt = path[idx + 1]
                    dx_t, dy_t = nxt[0] - prev[0], nxt[1] - prev[1]
                else:
                    dx_t, dy_t = pos[0] - prev[0], pos[1] - prev[1]

                perp = (
                    [(0, -1), (0, 1), (-1, 0), (1, 0)]
                    if abs(dx_t) >= abs(dy_t)
                    else [(-1, 0), (1, 0), (0, -1), (0, 1)]
                )
                path_cells = set(path)
                for dx, dy in perp:
                    yp = (pos[0] + dx, pos[1] + dy)
                    if yp in self.gs.blocked_static or yp in occupied or yp in path_cells:
                        continue
                    self.predicted[bid] = yp
                    break
                break

    def _build_moving_obstacles(self, bid: int) -> list[tuple[tuple[int, int], tuple[int, int]]]:
        """Build moving obstacle list for temporal BFS (other bots only)."""
        decided: set[int] = getattr(self, "_decided", set())
        obstacles: list[tuple[tuple[int, int], tuple[int, int]]] = []
        for b in self.bots:
            if b["id"] == bid:
                continue
            cur: tuple[int, int] = tuple(b["position"])
            if b["id"] < bid and b["id"] in decided:
                pred: tuple[int, int] = self.predicted.get(b["id"], cur)
            else:
                pred = cur  # higher ID or undecided: treat as stationary
            obstacles.append((cur, pred))
        return obstacles

    def _bfs_smart(
        self,
        bid: int,
        pos: tuple[int, int],
        target: tuple[int, int],
        blocked: set[tuple[int, int]],
    ) -> tuple[int, int] | None:
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
            cached = self.gs.get_cached_next_step(bid, pos, target, dynamic_blocked, current_round)
            if cached is not None and cached not in blocked:
                if not self._would_oscillate(bid, cached):
                    next_step: tuple[int, int] = cached
                    return next_step
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
        result: tuple[int, int] | None = None
        if self.cfg.use_temporal_bfs:
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
        cache_miss = not had_cache or bid not in self.gs.bot_planned_paths
        if use_cache and result is not None and cache_miss:
            self.gs.store_path_for_step(bid, pos, result, target, current_round)

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
        return bool(next_pos == history[-2])

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
            fallback_pos: tuple[int, int] | None = None
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
        """Build blocked set for a specific bot (static + nearby other bots).

        The server processes bots sequentially by ID. Lower-ID bots have
        already moved (use predicted position), higher-ID bots haven't
        moved yet (use current position).
        """
        pos: tuple[int, int] = tuple(self.bots_by_id[bid]["position"])
        max_dist: float = self.cfg.blocking_radius
        decided: set[int] = getattr(self, "_decided", set())
        other: set[tuple[int, int]] = set()
        for b in self.bots:
            if b["id"] == bid:
                continue
            # Server processes lower IDs first: they're at predicted pos.
            # Higher IDs haven't moved: they're at current pos.
            # Only trust predictions for bots the planner has decided.
            if b["id"] < bid and b["id"] in decided:
                bp: tuple[int, int] = self.predicted.get(b["id"], tuple(b["position"]))
            else:
                bp = tuple(b["position"])
            if max_dist == float("inf") or (abs(bp[0] - pos[0]) + abs(bp[1] - pos[1])) <= max_dist:
                other.add(bp)
        blocked_set: set[tuple[int, int]] = self.gs.blocked_static | other
        return blocked_set
