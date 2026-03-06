"""Idle positioning and dropoff clearing for RoundPlanner."""

from pathfinding import DIRECTIONS, direction_to


class IdleMixin:
    """Mixin providing idle bot positioning and dropoff area clearing."""

    def _try_clear_dropoff(self, bid, bx, by, pos, blocked):
        if len(self.bots) <= 1:
            return False
        dist_to_drop = self.gs.dist_static(pos, self.drop_off)
        if dist_to_drop > 3:
            return False
        best_away = None
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
                bid, bx, by,
                {"bot": bid, "action": direction_to(bx, by, best_away[0], best_away[1])},
            )
            return True
        return False

    def _try_idle_positioning(self, bid, bx, by, pos, blocked):
        """Unified idle positioning: spread out from dropoff and other bots."""
        if len(self.bots) <= 1:
            return False

        other_bot_positions = [
            tuple(b["position"]) for b in self.bots if b["id"] != bid
        ]

        def _score(p):
            """Lower is better."""
            s = 0.0
            drop_dist = self.gs.dist_static(p, self.drop_off)
            if drop_dist <= 3:
                s += (4 - drop_dist) * 3
            for ob_pos in other_bot_positions:
                ob_dist = abs(p[0] - ob_pos[0]) + abs(p[1] - ob_pos[1])
                if ob_dist <= 2:
                    s += (3 - ob_dist) * 2
            return s

        stay_score = _score(pos)

        best = None
        best_score = stay_score
        for dx, dy in DIRECTIONS:
            npos = (bx + dx, by + dy)
            if npos in blocked:
                continue
            s = _score(npos)
            if s < best_score:
                best_score = s
                best = npos

        if best:
            self._emit(
                bid, bx, by,
                {"bot": bid, "action": direction_to(bx, by, best[0], best[1])},
            )
            return True
        return False
