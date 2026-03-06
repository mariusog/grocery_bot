"""Movement, collision avoidance, and action emission for RoundPlanner."""

from pathfinding import DIRECTIONS, bfs, bfs_temporal, direction_to, _predict_pos


class MovementMixin:
    """Mixin providing movement, BFS, and action emission methods."""

    def _emit(self, bid, bx, by, action_dict):
        """Record action with yield-redirect for higher-urgency bots."""
        if self._yield_to and action_dict["action"].startswith("move_"):
            predicted = _predict_pos(bx, by, action_dict["action"])
            if predicted in self._yield_to:
                action_dict = self._find_yield_alternative(bid, bx, by, predicted)

        self.actions.append(action_dict)
        self.predicted[bid] = _predict_pos(bx, by, action_dict["action"])

        if action_dict["action"] == "pick_up":
            self.gs.last_pickup[bid] = (action_dict["item_id"], len(self.bots_by_id[bid]["inventory"]))

    def _find_yield_alternative(self, bid, bx, by, blocked_target):
        occupied = {
            self.predicted.get(b["id"], tuple(b["position"]))
            for b in self.bots if b["id"] != bid
        }
        for dx, dy in DIRECTIONS:
            alt = (bx + dx, by + dy)
            if alt == blocked_target or alt in self.gs.blocked_static:
                continue
            if alt in occupied:
                continue
            return {"bot": bid, "action": direction_to(bx, by, alt[0], alt[1])}
        return {"bot": bid, "action": "wait"}

    def _build_moving_obstacles(self, bid):
        """Build moving obstacle list for temporal BFS (other bots only)."""
        obstacles = []
        for b in self.bots:
            if b["id"] == bid:
                continue
            cur = tuple(b["position"])
            pred = self.predicted.get(b["id"], cur)
            obstacles.append((cur, pred))
        return obstacles

    def _bfs_smart(self, bid, pos, target, blocked):
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

    def _emit_move(self, bid, bx, by, pos, target, blocked):
        """BFS to target and emit. Returns True if a move was emitted."""
        next_pos = self._bfs_smart(bid, pos, target, blocked)
        if next_pos:
            self._emit(
                bid, bx, by,
                {"bot": bid, "action": direction_to(bx, by, next_pos[0], next_pos[1])},
            )
            return True
        return False

    def _would_oscillate(self, bid, next_pos):
        """Check if moving to next_pos would create an oscillation pattern."""
        history = self.gs.bot_history.get(bid)
        if not history or len(history) < 2:
            return False
        return next_pos == history[-2]

    def _emit_move_or_wait(self, bid, bx, by, pos, target, blocked):
        """Move toward target with unstick fallback and oscillation detection."""
        next_pos = self._bfs_smart(bid, pos, target, blocked)

        if next_pos and self._would_oscillate(bid, next_pos):
            alt_pos = None
            for dx, dy in DIRECTIONS:
                npos = (bx + dx, by + dy)
                if npos not in blocked and npos != next_pos and not self._would_oscillate(bid, npos):
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
                bid, bx, by,
                {"bot": bid, "action": direction_to(bx, by, next_pos[0], next_pos[1])},
            )
        else:
            self._emit(bid, bx, by, {"bot": bid, "action": "wait"})

    def _build_blocked(self, bid):
        """Build blocked set for a specific bot (static + nearby other bots)."""
        pos = tuple(self.bots_by_id[bid]["position"])
        max_dist = 6 if len(self.bots) >= 5 else float("inf")
        other = set()
        for b in self.bots:
            if b["id"] == bid:
                continue
            bp = self.predicted.get(b["id"], tuple(b["position"]))
            if max_dist == float("inf") or (abs(bp[0] - pos[0]) + abs(bp[1] - pos[1])) <= max_dist:
                other.add(bp)
        return self.gs.blocked_static | other
