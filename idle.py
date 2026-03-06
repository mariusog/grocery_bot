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
        """Idle positioning: move toward item shelves while avoiding crowds.

        For large teams, idle bots move toward the center of item shelves
        so they're ready to pick up items when the next order activates.
        Also avoids dropoff area and other bots.
        """
        if len(self.bots) <= 1:
            return False

        other_bot_positions = [
            tuple(b["position"]) for b in self.bots if b["id"] != bid
        ]

        # Find target: center of item positions (where items are)
        item_target = None
        if len(self.bots) >= 3 and self.items:
            # Spread bots across item area: use hash of bot ID to pick a zone
            item_positions = [tuple(it["position"]) for it in self.items]
            if item_positions:
                # Divide items into zones by x-coordinate, assign bot to a zone
                xs = sorted(set(p[0] for p in item_positions))
                if xs:
                    zone_idx = bid % len(xs)
                    target_x = xs[zone_idx]
                    # Find closest item y in that column
                    col_ys = [p[1] for p in item_positions if p[0] == target_x]
                    if col_ys:
                        target_y = col_ys[len(col_ys) // 2]
                        item_target = (target_x, target_y)

        def _score(p):
            """Lower is better."""
            s = 0.0
            # Penalize being near dropoff
            drop_dist = self.gs.dist_static(p, self.drop_off)
            if drop_dist <= 3:
                s += (4 - drop_dist) * 3
            # Penalize being near other bots
            for ob_pos in other_bot_positions:
                ob_dist = abs(p[0] - ob_pos[0]) + abs(p[1] - ob_pos[1])
                if ob_dist <= 2:
                    s += (3 - ob_dist) * 2
            # Reward being near item shelves
            if item_target:
                item_dist = abs(p[0] - item_target[0]) + abs(p[1] - item_target[1])
                s += item_dist * 0.5
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
