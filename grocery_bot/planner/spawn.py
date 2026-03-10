"""Spawn-phase dispersal for all team sizes.

When bots start stacked at spawn, they all BFS toward the same nearest
items and convoy in a single file.  This mixin assigns each bot a
unique dispersal target in a different vertical zone of the item grid
so they spread across the map after exiting spawn.

The dispersal only overrides idle/unassigned bots — assigned bots
follow their normal pickup routes.
"""

from typing import Any

from grocery_bot.planner._base import PlannerBase


class SpawnMixin(PlannerBase):
    """Mixin providing opening-round dispersal for all team sizes."""

    def _infer_spawn_origin(self) -> tuple[int, int] | None:
        """Persist the clustered spawn cell inferred from bot positions."""
        if self.gs.spawn_origin is not None:
            return tuple(self.gs.spawn_origin)  # type: ignore[return-value]

        counts: dict[tuple[int, int], int] = {}
        for b in self.bots:
            pos = tuple(b["position"])
            counts[pos] = counts.get(pos, 0) + 1
        if not counts:
            return None

        spawn, count = max(counts.items(), key=lambda entry: entry[1])
        if count >= 2:
            self.gs.spawn_origin = spawn
            return spawn
        return None

    def _compute_dispersal_targets(self) -> None:
        """Assign each bot a dispersal target in a unique vertical zone."""
        if self.gs.spawn_dispersal_targets is not None:
            return

        num_bots = len(self.bots)
        if num_bots <= 1:
            self.gs.spawn_dispersal_targets = {}
            return

        item_ys = sorted({tuple(it["position"])[1] for it in self.items})
        if not item_ys:
            self.gs.spawn_dispersal_targets = {}
            return

        spawn_pos = self._get_spawn_pos()
        zones = self._split_into_zones(item_ys, num_bots)
        targets = self._assign_zone_targets(zones, spawn_pos)
        self.gs.spawn_dispersal_targets = targets

    def _split_into_zones(
        self, item_ys: list[int], num_bots: int,
    ) -> list[list[int]]:
        """Split item Y-rows into num_bots vertical zones."""
        n_zones = min(num_bots, len(item_ys))
        if n_zones <= 1:
            return [item_ys]

        zones: list[list[int]] = [[] for _ in range(n_zones)]
        for i, y in enumerate(item_ys):
            zone_idx = i * n_zones // len(item_ys)
            zones[zone_idx].append(y)
        return [z for z in zones if z]

    def _assign_zone_targets(
        self,
        zones: list[list[int]],
        spawn_pos: tuple[int, int],
    ) -> dict[int, tuple[int, int]]:
        """Assign each bot a walkable target cell near its zone's items."""
        num_bots = len(self.bots)
        targets: dict[int, tuple[int, int]] = {}
        if not zones:
            return targets

        row_cells: dict[int, list[tuple[int, int]]] = {}
        for it in self.items:
            ipos = tuple(it["position"])
            for cell in self.gs.adj_cache.get(ipos, []):
                row_cells.setdefault(cell[1], []).append(cell)

        for bid in range(num_bots):
            zone_idx = bid % len(zones)
            zone_ys = zones[zone_idx]
            best = self._find_zone_target(zone_ys, row_cells, spawn_pos)
            if best is not None:
                targets[bid] = best
        return targets

    def _get_spawn_pos(self) -> tuple[int, int]:
        """Get spawn position from bots or stored origin."""
        if self.gs.spawn_origin is not None:
            return tuple(self.gs.spawn_origin)  # type: ignore[return-value]
        return tuple(self.bots[0]["position"])  # type: ignore[return-value]

    def _find_zone_target(
        self,
        zone_ys: list[int],
        row_cells: dict[int, list[tuple[int, int]]],
        spawn_pos: tuple[int, int],
    ) -> tuple[int, int] | None:
        """Find the best walkable cell in a vertical zone."""
        mid_y = zone_ys[len(zone_ys) // 2]
        candidates: list[tuple[int, int]] = []
        for y in zone_ys:
            candidates.extend(row_cells.get(y, []))
        if not candidates:
            return None

        return min(
            candidates,
            key=lambda c: (
                abs(c[1] - mid_y),
                self.gs.dist_static(spawn_pos, c),
            ),
        )

    def _step_spawn_dispersal(self, ctx: Any) -> bool:
        """Route unassigned bots toward diverse zones during opening."""
        if self.cfg.num_bots < 10:
            return False
        if self.current_round >= self.cfg.spawn_dispersal_max_rounds():
            return False
        if ctx.inv or ctx.has_active:
            return False

        # Skip bots that have active pickup assignments
        if self.bot_assignments.get(ctx.bid):
            return False

        # Stop dispersing when an active item is adjacent -- pick it instead.
        from grocery_bot.pathfinding import DIRECTIONS
        for dx, dy in DIRECTIONS:
            for it in self.items_at_pos.get((ctx.bx + dx, ctx.by + dy), []):
                if self._is_available(it) and self.net_active.get(it["type"], 0) > 0:
                    return False

        self._infer_spawn_origin()
        self._compute_dispersal_targets()

        targets = self.gs.spawn_dispersal_targets
        if not targets or ctx.bid not in targets:
            return False

        target = targets[ctx.bid]
        if ctx.pos == target:
            return False

        return self._emit_move(
            ctx.bid, ctx.bx, ctx.by, ctx.pos, target, ctx.blocked,
        )
