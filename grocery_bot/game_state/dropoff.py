"""Dropoff congestion management for GameState."""

from typing import Optional

from grocery_bot.constants import (
    DROPOFF_CONGESTION_RADIUS,
    DROPOFF_WAIT_DISTANCE,
    MAX_APPROACH_SLOTS,
)
from grocery_bot.pathfinding import bfs_all


class DropoffMixin:
    """Mixin providing dropoff area congestion detection and avoidance."""

    def _precompute_dropoff_zones(self, drop_off: tuple[int, int]) -> None:
        """Precompute dropoff-adjacent cells, approach zone, and wait zone."""
        dists = bfs_all(drop_off, self.blocked_static)

        self.dropoff_adjacents = []
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            adj = (drop_off[0] + dx, drop_off[1] + dy)
            if adj in dists:
                self.dropoff_adjacents.append(adj)

        self.dropoff_approach_cells = sorted(
            (pos for pos, d in dists.items() if 0 < d <= DROPOFF_CONGESTION_RADIUS),
            key=lambda p: dists[p],
        )
        self.dropoff_approach_set = set(self.dropoff_approach_cells)
        self.dropoff_approach_set.add(drop_off)

        self.dropoff_wait_cells = sorted(
            (pos for pos, d in dists.items() if d == DROPOFF_WAIT_DISTANCE),
            key=lambda p: abs(p[0] - drop_off[0]),
        )

    def get_dropoff_approach_target(
        self,
        bot_id: int,
        bot_pos: tuple[int, int],
        drop_off: tuple[int, int],
        delivering_bots: list[tuple[int, tuple[int, int]]],
    ) -> tuple[tuple[int, int], bool]:
        """Determine where a delivering bot should path to, managing congestion."""
        if not self.dropoff_approach_cells:
            return drop_off, False

        my_dist = self.dist_static(bot_pos, drop_off)

        closer_bots = 0
        for other_id, other_pos in delivering_bots:
            if other_id == bot_id:
                continue
            other_dist = self.dist_static(other_pos, drop_off)
            if other_dist < my_dist or (other_dist == my_dist and other_id < bot_id):
                closer_bots += 1

        if closer_bots < MAX_APPROACH_SLOTS:
            return drop_off, False

        if self.dropoff_wait_cells:
            occupied = {pos for _, pos in delivering_bots if _ != bot_id}
            for wc in self.dropoff_wait_cells:
                if wc not in occupied and wc != bot_pos:
                    return wc, True
            best_wc = min(
                self.dropoff_wait_cells,
                key=lambda p: self.dist_static(bot_pos, p),
            )
            return best_wc, True

        return drop_off, False

    def is_dropoff_congested(
        self,
        drop_off: tuple[int, int],
        bot_positions: list[tuple[int, int]],
    ) -> bool:
        """Return True if the dropoff area is congested."""
        approach_set = set(self.dropoff_approach_cells)
        approach_set.add(drop_off)
        count = sum(1 for pos in bot_positions if pos in approach_set)
        return count > MAX_APPROACH_SLOTS

    def get_avoidance_target(
        self,
        bot_pos: tuple[int, int],
        drop_off: tuple[int, int],
    ) -> Optional[tuple[int, int]]:
        """Return a position away from the dropoff for non-delivering bots."""
        my_dist = self.dist_static(bot_pos, drop_off)
        if my_dist > DROPOFF_CONGESTION_RADIUS:
            return None

        best: Optional[tuple[int, int]] = None
        best_d = float("inf")
        candidates = self.idle_spots + self.dropoff_wait_cells
        for pos in candidates:
            d_to_drop = self.dist_static(pos, drop_off)
            if d_to_drop > DROPOFF_CONGESTION_RADIUS:
                d_from_bot = self.dist_static(bot_pos, pos)
                if d_from_bot < best_d:
                    best_d = d_from_bot
                    best = pos
        return best

    def update_round_positions(
        self,
        bot_positions: dict[int, tuple[int, int]],
        drop_off: tuple[int, int],
    ) -> None:
        """Called at the start of each round to track bot positions."""
        self._round_bot_positions = dict(bot_positions)
        self._round_bot_targets = {}
        self._round_drop_off = drop_off

    def notify_bot_target(self, bot_id: int, target: Optional[tuple[int, int]]) -> None:
        """Record that a bot is heading toward a specific target."""
        self._round_bot_targets[bot_id] = target

    def count_bots_near_dropoff(self, exclude_bot: int = -1) -> int:
        """Count bots currently within the dropoff approach zone."""
        if not self.dropoff_approach_cells or self._round_drop_off is None:
            return 0
        approach_set = set(self.dropoff_approach_cells)
        approach_set.add(self._round_drop_off)
        count = 0
        for bid, pos in self._round_bot_positions.items():
            if bid == exclude_bot:
                continue
            if pos in approach_set:
                count += 1
        return count

    def count_bots_targeting_dropoff(self, exclude_bot: int = -1) -> int:
        """Count bots whose target is the dropoff cell."""
        if self._round_drop_off is None:
            return 0
        count = 0
        for bid, target in self._round_bot_targets.items():
            if bid == exclude_bot:
                continue
            if target == self._round_drop_off:
                count += 1
        return count
