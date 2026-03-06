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
        for dx, dy in DIRECTIONS:
            alt = (bx + dx, by + dy)
            if alt == blocked_target or alt in self.gs.blocked_static:
                continue
            if alt in occupied:
                continue
            return {"bot": bid, "action": direction_to(bx, by, alt[0], alt[1])}
        return {"bot": bid, "action": "wait"}

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

            # Delivering bots with full inventory or no items left to pick
            if has_active and (
                len(inv) >= MAX_INVENTORY or self.active_on_shelves == 0
            ):
                nxt = bfs(pos, self.drop_off, self.gs.blocked_static)
                if nxt:
                    self.predicted[bid] = nxt
                    continue

            # Bots at dropoff with active items will drop off (stay put)
            if pos == self.drop_off and has_active:
                self.predicted[bid] = pos
                continue

            # Bots with assigned items move toward first assigned item
            if bid in self.bot_assignments and self.bot_assignments[bid]:
                first_item = self.bot_assignments[bid][0]
                cell, _ = self.gs.find_best_item_target(pos, first_item)
                if cell:
                    nxt = bfs(pos, cell, self.gs.blocked_static)
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
        """Use temporal BFS for multi-bot, standard BFS for single bot."""
        if len(self.bots) > 1:
            obstacles = self._build_moving_obstacles(bid)
            result = bfs_temporal(pos, target, self.gs.blocked_static, obstacles)
            if result and result not in blocked:
                return result
        # Fallback to standard BFS
        result = bfs(pos, target, blocked)
        if result and result in blocked:
            return None
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
        """Check if moving to next_pos would create an oscillation pattern."""
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
        """Move toward target with unstick fallback and oscillation detection."""
        next_pos = self._bfs_smart(bid, pos, target, blocked)

        if next_pos and self._would_oscillate(bid, next_pos):
            alt_pos: Optional[tuple[int, int]] = None
            for dx, dy in DIRECTIONS:
                npos = (bx + dx, by + dy)
                if (
                    npos not in blocked
                    and npos != next_pos
                    and not self._would_oscillate(bid, npos)
                ):
                    alt_pos = npos
                    break
            if alt_pos:
                next_pos = alt_pos

        if not next_pos:
            for dx, dy in DIRECTIONS:
                npos = (bx + dx, by + dy)
                if npos not in blocked:
                    next_pos = npos
                    break
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
