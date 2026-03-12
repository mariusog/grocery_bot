"""Spawn-phase dispersal for all team sizes.

When bots start stacked at spawn, they all BFS toward the same nearest
items and convoy in a single file.  This mixin assigns each bot a
unique dispersal target at the bottom of each aisle lane so they spread
across the map while staying close to the dropoff.

The dispersal only overrides idle/unassigned bots — assigned bots
follow their normal pickup routes.
"""

from typing import Any

from grocery_bot.constants import MIN_LANE_ADJ_CELLS
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

        spawn, count = max(counts.items(), key=lambda entry: (entry[1], entry[0]))
        if count >= 2:
            self.gs.spawn_origin = spawn
            return spawn
        return None

    def _compute_dispersal_targets(self) -> None:
        """Assign each bot a dispersal target at the bottom of an aisle lane."""
        if self.gs.spawn_dispersal_targets is not None:
            return
        if not self.cfg.multi_bot:
            self.gs.spawn_dispersal_targets = {}
            return

        # Try lane-based dispersal first (positions bots near items AND dropoff)
        lane_targets = self._build_lane_targets()
        if lane_targets:
            self.gs.spawn_dispersal_targets = lane_targets
            self.gs.spawn_lane_dispersal = True
            return

        # Fallback to Y-zone dispersal for unusual map layouts
        num_bots = len(self.bots)
        item_ys = sorted({tuple(it["position"])[1] for it in self.items})
        if not item_ys:
            self.gs.spawn_dispersal_targets = {}
            return
        spawn_pos = self._get_spawn_pos()
        zones = self._split_into_zones(item_ys, num_bots)
        self.gs.spawn_dispersal_targets = self._assign_zone_targets(zones, spawn_pos)

    def _build_lane_targets(self) -> dict[int, tuple[int, int]] | None:
        """Build lane-based dispersal targets. Returns None if < 2 lanes.

        Only used for single-dropoff maps where clustering near the dropoff
        is beneficial. Multi-dropoff maps (Nightmare) need full map spread.
        """
        if len(self.drop_off_zones) > 1:
            return None
        lanes = self._find_aisle_lanes()
        if len(lanes) < 2:
            return None
        positions = self._lane_positions_near_dropoff(lanes)
        if not positions:
            return None
        result: dict[int, tuple[int, int]] = {}
        n = len(positions)
        for bid in range(len(self.bots)):
            result[bid] = positions[bid % n]
        return result

    def _find_aisle_lanes(self) -> list[int]:
        """Detect aisle lane X columns from item adjacency cells."""
        col_count: dict[int, int] = {}
        for adj_cells in self.gs.adj_cache.values():
            for cell in adj_cells:
                col_count[cell[0]] = col_count.get(cell[0], 0) + 1
        return sorted(x for x, cnt in col_count.items() if cnt >= MIN_LANE_ADJ_CELLS)

    def _lane_positions_near_dropoff(
        self, lanes: list[int]
    ) -> list[tuple[int, int]]:
        """For each lane, pick bottom and mid-corridor cells for spread.

        Returns up to 2*len(lanes) positions: bottom (max-Y) first, then
        mid-corridor for each lane, sorted by distance to dropoff.  This
        avoids duplication where N bots > N lanes meant two bots sharing
        the exact same target cell.
        """
        col_cells: dict[int, set[tuple[int, int]]] = {}
        for adj_cells in self.gs.adj_cache.values():
            for cell in adj_cells:
                col_cells.setdefault(cell[0], set()).add(cell)

        # Detect the mid-corridor: interior row with fewest walls.
        all_ys = {c[1] for cells in col_cells.values() for c in cells}
        if all_ys:
            min_y, max_y = min(all_ys), max(all_ys)
            interior = range(min_y + 2, max_y - 1)
            mid_corridor = min(
                interior,
                key=lambda y: sum(1 for x in range(self.gs.grid_width) if (x, y) in self.gs.blocked_static),
                default=(min_y + max_y) // 2,
            )
        else:
            mid_corridor = 0

        bottom: list[tuple[float, tuple[int, int]]] = []
        mid: list[tuple[float, tuple[int, int]]] = []
        for x in lanes:
            cells = list(col_cells.get(x, []))
            if not cells:
                continue
            bot_cell = max(cells, key=lambda c: c[1])
            # Mid target is directly on the corridor row (walkable,
            # but not in adj_cache since there are no shelves there).
            mid_cell = (x, mid_corridor)
            d_bot = min(
                self.gs.dist_static(bot_cell, dz) for dz in self.drop_off_zones
            )
            d_mid = min(
                self.gs.dist_static(mid_cell, dz) for dz in self.drop_off_zones
            )
            bottom.append((d_bot, bot_cell))
            if mid_cell != bot_cell:
                mid.append((d_mid, mid_cell))
        bottom.sort()
        mid.sort()
        # Interleave bottom/mid so consecutive bots alternate exit
        # directions from spawn: LEFT (bottom) and UP (mid).
        result: list[tuple[int, int]] = []
        b_list = [p for _, p in bottom]
        m_list = [p for _, p in mid]
        for i in range(max(len(b_list), len(m_list))):
            if i < len(b_list):
                result.append(b_list[i])
            if i < len(m_list):
                result.append(m_list[i])
        return result

    # --- Y-zone fallback (for maps without clear aisle lanes) ---

    def _split_into_zones(
        self,
        item_ys: list[int],
        num_bots: int,
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
        """Move each bot straight to its dispersal target.

        Simple directional movement: reduce the larger delta first.
        Once a bot arrives it is permanently released.
        """
        if not self.cfg.use_spawn_dispersal:
            return False
        if self.current_round >= self.cfg.spawn_dispersal_max_rounds():
            return False

        is_lane = getattr(self.gs, "spawn_lane_dispersal", False)

        # Y-zone fallback (Nightmare) defers to assignments.
        if not is_lane:
            if ctx.inv or ctx.has_active:
                return False
            if self.bot_assignments.get(ctx.bid):
                return False

        self._infer_spawn_origin()
        self._compute_dispersal_targets()

        targets = self.gs.spawn_dispersal_targets
        if not targets or ctx.bid not in targets:
            return False

        target = targets[ctx.bid]
        done: set[int] = getattr(self.gs, "spawn_dispersal_done", set())
        if not hasattr(self.gs, "spawn_dispersal_done"):
            self.gs.spawn_dispersal_done = done
        if ctx.bid in done:
            return False
        if ctx.pos == target:
            done.add(ctx.bid)
            return False

        if not is_lane:
            return self._emit_move(
                ctx.bid, ctx.bx, ctx.by, ctx.pos, target, ctx.blocked,
            )

        # UP-stream bots go Y-first to split away from the bottom corridor.
        spawn = self.gs.spawn_origin
        y_first = bool(spawn and (spawn[1] - target[1]) > 4)
        return self._move_toward(ctx, target, y_first=y_first)

    def _move_toward(
        self, ctx: Any, target: tuple[int, int], *, y_first: bool,
    ) -> bool:
        """Move one step toward target along the preferred axis."""
        dx = target[0] - ctx.bx
        dy = target[1] - ctx.by
        candidates: list[tuple[tuple[int, int], str]] = []
        if dy != 0:
            step_y = (ctx.bx, ctx.by + (1 if dy > 0 else -1))
            candidates.append((step_y, "move_down" if dy > 0 else "move_up"))
        if dx != 0:
            step_x = (ctx.bx + (1 if dx > 0 else -1), ctx.by)
            candidates.append((step_x, "move_right" if dx > 0 else "move_left"))
        if not y_first:
            candidates.reverse()
        for step, action in candidates:
            if step not in ctx.blocked:
                self._emit(
                    ctx.bid, ctx.bx, ctx.by,
                    {"bot": ctx.bid, "action": action},
                )
                return True
        return False
