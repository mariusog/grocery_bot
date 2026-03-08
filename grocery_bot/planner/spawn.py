"""Spawn-phase dispersal for very large teams."""

from typing import Optional

from grocery_bot.pathfinding import DIRECTIONS, direction_to
from grocery_bot.constants import (
    SPAWN_CLUSTER_DIVISOR,
    SPAWN_CLUSTER_MIN_BOTS,
    SPAWN_DISPERSAL_MAX_ROUNDS,
    SPAWN_DISPERSAL_TEAM_MIN,
)


class SpawnMixin:
    """Mixin providing opening-round spawn dispersal priority."""

    def _infer_spawn_origin(self) -> Optional[tuple[int, int]]:
        """Persist the clustered spawn cell inferred from bot positions."""
        if self.gs.spawn_origin is not None:
            return self.gs.spawn_origin

        counts: dict[tuple[int, int], int] = {}
        for bot in self.bots:
            pos = tuple(bot["position"])
            counts[pos] = counts.get(pos, 0) + 1
        if not counts:
            return None

        spawn, count = max(counts.items(), key=lambda entry: entry[1])
        clustered_min = max(SPAWN_CLUSTER_MIN_BOTS, len(self.bots) // SPAWN_CLUSTER_DIVISOR)
        if count >= clustered_min:
            self.gs.spawn_origin = spawn
            return spawn
        return None

    def _spawn_target_hint(self, bid: int, spawn: tuple[int, int]) -> tuple[int, int]:
        """Return the best known productive target for a queued spawn bot."""
        if self.bot_has_active.get(bid, False):
            return self._nearest_dropoff(spawn)

        assigned = self.bot_assignments.get(bid)
        if assigned:
            cell, _ = self.gs.find_best_item_target(spawn, assigned[0])
            if cell is not None:
                return cell

        if bid in self.preview_bot_ids and self.preview and self.net_preview:
            best_cell: Optional[tuple[int, int]] = None
            best_dist = float("inf")
            for item, _ in self._iter_needed_items(self.net_preview):
                cell, dist = self.gs.find_best_item_target(spawn, item)
                if cell is not None and dist < best_dist:
                    best_cell = cell
                    best_dist = dist
            if best_cell is not None:
                return best_cell

        return self._nearest_dropoff(spawn)

    def _spawn_priority_key(
        self, bid: int, exit_cell: tuple[int, int], spawn: tuple[int, int]
    ) -> tuple[int, int, float, int]:
        """Rank waiting spawn bots by productivity for a given exit."""
        if self.bot_has_active.get(bid, False):
            priority = 0
        elif self.bot_assignments.get(bid):
            priority = 1
        elif bid in self.preview_bot_ids:
            priority = 2
        else:
            priority = 3

        dx = exit_cell[0] - spawn[0]
        dy = exit_cell[1] - spawn[1]
        if dy < 0:
            spread_rank = bid
        elif dx < 0:
            spread_rank = -bid
        elif dy > 0:
            spread_rank = -bid
        else:
            spread_rank = bid

        target = self._spawn_target_hint(bid, spawn)
        dist = self.gs.dist_static(exit_cell, target)
        return (priority, spread_rank, dist, bid)

    def _select_spawn_exit_bots(
        self, spawn: tuple[int, int]
    ) -> dict[int, tuple[int, int]]:
        """Assign the currently-open spawn exits to the best waiting bots."""
        waiting = [
            bot["id"]
            for bot in self.bots
            if tuple(bot["position"]) == spawn
            and not bot["inventory"]
            and (
                self.bot_has_active.get(bot["id"], False)
                or self.bot_assignments.get(bot["id"])
            )
        ]
        if not waiting:
            return {}

        exits = [
            (spawn[0] + dx, spawn[1] + dy)
            for dx, dy in DIRECTIONS
            if (spawn[0] + dx, spawn[1] + dy) not in self.gs.blocked_static
        ]
        assignments: dict[int, tuple[int, int]] = {}
        used: set[int] = set()
        for exit_cell in exits:
            available = [bid for bid in waiting if bid not in used]
            if not available:
                continue
            chosen = min(
                available,
                key=lambda bid: self._spawn_priority_key(bid, exit_cell, spawn),
            )
            assignments[chosen] = exit_cell
            used.add(chosen)
        return assignments

    def _step_spawn_dispersal(self, ctx) -> bool:
        """Reserve early spawn exits for the most productive waiting bots."""
        if len(self.bots) < SPAWN_DISPERSAL_TEAM_MIN:
            return False
        if self.current_round >= SPAWN_DISPERSAL_MAX_ROUNDS or ctx.inv:
            return False

        spawn = self._infer_spawn_origin()
        if spawn is None or ctx.pos != spawn:
            return False

        selected = self._select_spawn_exit_bots(spawn)
        if not selected:
            return False
        target = selected.get(ctx.bid)
        if target is None:
            self._emit(ctx.bid, ctx.bx, ctx.by, {"bot": ctx.bid, "action": "wait"})
            return True

        self._emit(
            ctx.bid,
            ctx.bx,
            ctx.by,
            {"bot": ctx.bid, "action": direction_to(ctx.bx, ctx.by, target[0], target[1])},
        )
        return True
