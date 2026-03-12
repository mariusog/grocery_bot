"""Speculative item pickup for idle bots on large teams.

When there are more bots than items to pick up, idle bots speculatively
grab items from shelves.  If those items match a future order the bot
can deliver immediately, shaving entire pickup-travel cycles.
"""

from typing import Any

from grocery_bot.constants import (
    MAX_INVENTORY,
    SPEC_MAX_TEAM_COPIES,
)
from grocery_bot.pathfinding import DIRECTIONS
from grocery_bot.planner._base import PlannerBase


class SpeculativeMixin(PlannerBase):
    """Mixin providing speculative item pickup for idle bots."""

    def _assign_speculative_targets(self) -> None:
        """Centralized assignment of idle bots to preview items.

        Uses map intelligence: items far from dropoff are assigned first
        (expensive to pick later). Each bot gets a unique target.
        """
        self.spec_assignments: dict[int, dict[str, Any]] = {}
        _do_preview = bool(self.preview and self.net_preview and self.cfg.enable_spec_assignment)
        _do_oracle = bool(
            self.oracle_needs and self.cfg.enable_speculative and self.cfg.num_bots < 15
        )
        if not _do_preview and not _do_oracle:
            return

        # Identify idle bots: no active assignment, no active items, has space
        idle_bids: list[int] = []
        for b in self.bots:
            bid = b["id"]
            if self.bot_has_active.get(bid, False):
                continue
            if self.bot_assignments.get(bid):
                continue
            if len(b["inventory"]) >= MAX_INVENTORY:
                continue
            idle_bids.append(bid)
        if not idle_bids:
            return

        # Collect preview items on shelves, ranked by dropoff distance DESC
        preview_items: list[tuple[float, dict[str, Any]]] = []
        seen_types: set[str] = set()
        for item_type, count in self.net_preview.items() if _do_preview else ():
            if count <= 0:
                continue
            for it in self.items_by_type.get(item_type, []):
                if not self._is_available(it):
                    continue
                if it["type"] in seen_types:
                    continue
                ipos = tuple(it["position"])
                nd = self._nearest_dropoff(ipos)
                d_drop = self.gs.dist_static(ipos, nd)
                preview_items.append((d_drop, it))
                seen_types.add(it["type"])

        # Sort far items first (highest dropoff distance)
        preview_items.sort(key=lambda x: -x[0])

        # Greedy match: for each item, assign the nearest idle bot
        assigned_bids: set[int] = set()
        for _d_drop, item in preview_items:
            if not idle_bids:
                break
            best_bid: int | None = None
            best_dist = float("inf")
            for bid in idle_bids:
                if bid in assigned_bids:
                    continue
                bpos = tuple(self.bots_by_id[bid]["position"])
                cell, d = self.gs.find_best_item_target(bpos, item)
                if cell is not None and d < best_dist:
                    best_dist = d
                    best_bid = bid
            if best_bid is not None:
                self.spec_assignments[best_bid] = item
                assigned_bids.add(best_bid)

        # Phase 2: Pipeline — pre-assign items to bots about to finish delivery
        self._assign_pipeline_targets(assigned_bids)

        # Phase 3: Assign oracle items to remaining idle bots
        if _do_oracle:
            for t, count in self.oracle_needs.items():
                if count <= 0:
                    continue
                remaining = [b for b in idle_bids if b not in assigned_bids]
                if not remaining:
                    break
                for it in self.items_by_type.get(t, []):
                    if not self._is_available(it):
                        continue
                    best_bid = None
                    best_dist = float("inf")
                    for bid in remaining:
                        bpos = tuple(self.bots_by_id[bid]["position"])
                        cell, d = self.gs.find_best_item_target(bpos, it)
                        if cell is not None and d < best_dist:
                            best_dist, best_bid = d, bid
                    if best_bid is not None:
                        self.spec_assignments[best_bid] = it
                        assigned_bids.add(best_bid)
                        break

    def _assign_pipeline_targets(self, assigned_bids: set[int]) -> None:
        """Pre-assign preview/oracle items to bots about to finish delivery."""
        if not self.cfg.enable_spec_assignment:
            return
        queue = getattr(self.gs, "delivery_queue", [])
        taken = {it["id"] for it in self.spec_assignments.values()}
        for bid in queue:
            if bid in assigned_bids or bid in self.spec_assignments:
                continue
            b = self.bots_by_id.get(bid)
            if not b:
                continue
            nd = self._nearest_dropoff(tuple(b["position"]))
            if self.gs.dist_static(tuple(b["position"]), nd) > 3:
                continue
            best = self._find_pipeline_item(nd, taken)
            if best:
                self.spec_assignments[bid] = best
                taken.add(best["id"])
                assigned_bids.add(bid)

    def _find_pipeline_item(
        self, from_pos: tuple[int, int], taken_ids: set[str]
    ) -> dict[str, Any] | None:
        """Find best preview/oracle item reachable from a position."""
        best: dict[str, Any] | None = None
        best_d = float("inf")
        needs: dict[str, int] = dict(self.net_preview)
        for t, c in self.oracle_needs.items():
            needs[t] = needs.get(t, 0) + c
        for t, count in needs.items():
            if count <= 0:
                continue
            for it in self.items_by_type.get(t, []):
                if not self._is_available(it) or it["id"] in taken_ids:
                    continue
                cell, d = self.gs.find_best_item_target(from_pos, it)
                if cell and d < best_d:
                    best_d, best = d, it
                break
        return best

    def _is_preferred_spec_type(self, item_type: str) -> bool:
        """Prefer preview-needed types for speculative pickup when available."""
        return bool(
            self.cfg.prefer_preview_spec and self.preview and self.net_preview.get(item_type, 0) > 0
        )

    def _step_oracle_prepick(self, ctx: Any) -> bool:
        """Pre-pick items for oracle-known future orders (N+2..N+K).

        For small teams (1-4 bots) where enable_speculative is off, this
        enables oracle-guided pickup. Large teams use _step_speculative_pickup
        which already incorporates oracle preference via _find_spec_target.
        """
        if not self.oracle_needs or ctx.has_active:
            return False
        if len(ctx.inv) >= MAX_INVENTORY:
            return False
        if self.bot_assignments.get(ctx.bid):
            return False
        spec_item = self.spec_assignments.get(ctx.bid)
        if spec_item and self._is_available(spec_item):
            return self._act_on_spec_assignment(
                ctx.bid, ctx.bx, ctx.by, ctx.pos, spec_item, ctx.blocked
            )
        return self._try_speculative_pickup(ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.inv, ctx.blocked)

    def _step_speculative_pickup(self, ctx: Any) -> bool:
        """Speculatively pick up items when idle (large teams)."""
        if not self.cfg.enable_speculative:
            return False
        if ctx.has_active or len(ctx.inv) >= MAX_INVENTORY:
            return False
        # Don't fill last slot with speculative when active items need picking.
        # Keeps 1 slot free so the bot can pick active items next round.
        free = MAX_INVENTORY - len(ctx.inv)
        if free <= 1 and self.active_on_shelves > 0 and self.cfg.reserve_last_slot_for_spec:
            return False
        has_assignment = ctx.bid in self.bot_assignments and bool(self.bot_assignments[ctx.bid])
        if has_assignment:
            return False
        # Use centralized spec assignment if available
        spec_item = self.spec_assignments.get(ctx.bid)
        if spec_item and self._is_available(spec_item):
            return self._act_on_spec_assignment(
                ctx.bid, ctx.bx, ctx.by, ctx.pos, spec_item, ctx.blocked
            )
        return self._try_speculative_pickup(ctx.bid, ctx.bx, ctx.by, ctx.pos, ctx.inv, ctx.blocked)

    def _act_on_spec_assignment(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        item: dict[str, Any],
        blocked: set[tuple[int, int]],
    ) -> bool:
        """Act on a centralized speculative assignment."""
        ipos = tuple(item["position"])
        # Adjacent — pick it up
        if abs(bx - ipos[0]) + abs(by - ipos[1]) == 1:
            self.claimed.add(item["id"])
            self._speculative_pickers += 1
            self._emit(bid, bx, by, self._pickup(bid, item))
            return True
        # Walk toward it
        cell, _d = self.gs.find_best_item_target(pos, item)
        if cell:
            self.claimed.add(item["id"])
            self._speculative_pickers += 1
            return self._emit_move(bid, bx, by, pos, cell, blocked)
        return False

    def _try_oracle_pickup(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        inv: list[str],
        blocked: set[tuple[int, int]],
    ) -> bool:
        """Pick up items needed by oracle-known future orders only."""
        bot_types = set(inv)
        # Pass 1: adjacent oracle item (zero travel cost)
        for dx, dy in DIRECTIONS:
            for it in self.items_at_pos.get((bx + dx, by + dy), []):
                if not self._is_available(it):
                    continue
                t = it["type"]
                if t in bot_types:
                    continue
                if self.oracle_needs.get(t, 0) <= 0:
                    continue
                self.claimed.add(it["id"])
                self._speculative_pickers += 1
                self._emit(bid, bx, by, self._pickup(bid, it))
                return True
        # Pass 2: walk to nearest oracle-needed item
        best_item: dict[str, Any] | None = None
        best_cell: tuple[int, int] | None = None
        best_dist = float("inf")
        for it in self.items:
            if not self._is_available(it):
                continue
            t = it["type"]
            if t in bot_types or self.oracle_needs.get(t, 0) <= 0:
                continue
            cell, d = self.gs.find_best_item_target(pos, it)
            if cell and d < best_dist:
                best_dist = d
                best_item = it
                best_cell = cell
        if best_item and best_cell:
            self.claimed.add(best_item["id"])
            self._speculative_pickers += 1
            return self._emit_move(bid, bx, by, pos, best_cell, blocked)
        return False

    def _try_spec_adjacent_only(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        inv: list[str],
        blocked: set[tuple[int, int]],
    ) -> bool:
        """Adjacent-only speculative pickup (no walk-to-target)."""
        max_spec = self.cfg.max_spec_pickers()
        if self._speculative_pickers >= max_spec:
            return False
        team_type_count: dict[str, int] = {}
        for b in self.bots:
            for it_type in b["inventory"]:
                team_type_count[it_type] = team_type_count.get(it_type, 0) + 1
        item = self._find_spec_adjacent(bx, by, set(inv), team_type_count)
        if item:
            self.claimed.add(item["id"])
            self._spec_types_claimed.add(item["type"])
            self._speculative_pickers += 1
            self._emit(bid, bx, by, self._pickup(bid, item))
            return True
        return False

    def _try_speculative_pickup(
        self,
        bid: int,
        bx: int,
        by: int,
        pos: tuple[int, int],
        inv: list[str],
        blocked: set[tuple[int, int]],
    ) -> bool:
        """Pick up items speculatively for future orders."""
        max_spec = self.cfg.max_spec_pickers()
        if self._speculative_pickers >= max_spec:
            return False

        team_type_count: dict[str, int] = {}
        for b in self.bots:
            for it_type in b["inventory"]:
                team_type_count[it_type] = team_type_count.get(it_type, 0) + 1

        bot_types = set(inv)

        # Pass 1: adjacent pickup (zero travel cost — always take it)
        item = self._find_spec_adjacent(
            bx,
            by,
            bot_types,
            team_type_count,
        )
        if item:
            self.claimed.add(item["id"])
            self._spec_types_claimed.add(item["type"])
            self._speculative_pickers += 1
            self._emit(bid, bx, by, self._pickup(bid, item))
            return True

        # Pass 2: walk to nearest unclaimed item of an uncovered type
        target_item, target_cell = self._find_spec_target(
            pos,
            bot_types,
            team_type_count,
        )
        if not target_item or not target_cell:
            return False

        self.claimed.add(target_item["id"])
        self._spec_types_claimed.add(target_item["type"])
        self._speculative_pickers += 1
        return self._emit_move(bid, bx, by, pos, target_cell, blocked)

    def _find_spec_adjacent(
        self,
        bx: int,
        by: int,
        bot_types: set[str],
        team_type_count: dict[str, int],
    ) -> dict[str, Any] | None:
        """Find an adjacent item suitable for speculative pickup."""
        preview_item: dict[str, Any] | None = None
        fallback_item: dict[str, Any] | None = None
        for dx, dy in DIRECTIONS:
            for it in self.items_at_pos.get((bx + dx, by + dy), []):
                if not self._is_available(it):
                    continue
                t = it["type"]
                if t in self._spec_types_claimed:
                    continue
                if t in bot_types:
                    continue
                if team_type_count.get(t, 0) >= SPEC_MAX_TEAM_COPIES:
                    continue
                if self._is_preferred_spec_type(t):
                    preview_item = it
                    break
                if fallback_item is None:
                    fallback_item = it
            if preview_item is not None:
                return preview_item
        return fallback_item

    def _find_spec_target(
        self,
        pos: tuple[int, int],
        bot_types: set[str],
        team_type_count: dict[str, int],
    ) -> tuple[dict[str, Any] | None, tuple[int, int] | None]:
        """Find the nearest walkable item of an uncovered type."""
        best_item: dict[str, Any] | None = None
        best_cell: tuple[int, int] | None = None
        best_key: tuple[int, float, int] = (1, float("inf"), 1)
        for it in self.items:
            if not self._is_available(it):
                continue
            t = it["type"]
            if t in self._spec_types_claimed:
                continue
            if t in bot_types:
                continue
            if team_type_count.get(t, 0) >= SPEC_MAX_TEAM_COPIES:
                continue
            cell, d = self.gs.find_best_item_target(pos, it)
            is_preview = (
                self.cfg.prefer_preview_spec and self.preview and self.net_preview.get(t, 0) > 0
            )
            is_oracle = self.oracle_needs.get(t, 0) > 0
            # Preview: tier 0, Oracle: tier 0 always when data exists
            if is_preview:
                key = (0, d, 0)
            elif is_oracle:
                key = (0, d, 1)
            else:
                key = (1, d, 1)
            if cell and key < best_key:
                best_key = key
                best_item = it
                best_cell = cell
        return best_item, best_cell
