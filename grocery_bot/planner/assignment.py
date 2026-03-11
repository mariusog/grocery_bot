"""Bot-to-item assignment logic for RoundPlanner."""

from typing import Any

from grocery_bot.constants import (
    ASSIGNMENT_DROPOFF_WEIGHT,
    MAX_INVENTORY,
    MAX_PREVIEW_BOTS,
    ZONE_CROSS_PENALTY,
)
from grocery_bot.planner._base import PlannerBase


class AssignmentMixin(PlannerBase):
    """Mixin providing bot assignment, preview bot selection, and urgency."""

    def _is_delivering(self, bot: dict[str, Any]) -> bool:
        """True if bot is busy delivering (shouldn't count as idle)."""
        has_ai = self.bot_has_active[bot["id"]]
        return has_ai and (
            len(bot["inventory"]) >= MAX_INVENTORY
            or self.active_on_shelves == 0
            or self._is_at_any_dropoff(tuple(bot["position"]))
        )

    def _assign_preview_bot(self) -> None:
        """Assign bots furthest from remaining active items as preview-only bots.

        For 2+ bots, allow up to (num_idle - active_on_shelves - 1) preview bots,
        keeping at least 1 more idle bot than needed for active items.
        """
        idle_for_active: list[dict[str, Any]] = []
        for bot in self.bots:
            if self._is_delivering(bot):
                continue
            idle_for_active.append(bot)

        if len(idle_for_active) <= self.active_on_shelves:
            return

        active_item_positions: list[tuple[int, int]] = []
        for it, _ in self._iter_needed_items(self.net_active):
            cell, _ = self.gs.find_best_item_target(self.drop_off_zones[0], it)
            if cell:
                active_item_positions.append(cell)
        if not active_item_positions:
            return

        cx = sum(p[0] for p in active_item_positions) / len(active_item_positions)
        cy = sum(p[1] for p in active_item_positions) / len(active_item_positions)

        surplus = len(idle_for_active) - self.active_on_shelves
        if surplus <= 0:
            return
        if self.cfg.use_multi_preview_bots:
            max_preview = min(MAX_PREVIEW_BOTS, max(1, surplus - 1))
        else:
            max_preview = 1

        candidates: list[tuple[float, int]] = []
        for bot in idle_for_active:
            if self.bot_has_active[bot["id"]]:
                continue
            if len(bot["inventory"]) >= MAX_INVENTORY:
                continue
            bx, by = bot["position"]
            d = abs(bx - cx) + abs(by - cy)
            candidates.append((d, bot["id"]))

        candidates.sort(reverse=True)

        for i, (_, bid) in enumerate(candidates):
            if i >= max_preview:
                break
            self.preview_bot_ids.add(bid)

        if self.preview_bot_ids:
            self.preview_bot_id = min(self.preview_bot_ids)

    def _bot_delivery_completes_order(self, bot: dict[str, Any]) -> bool:
        """Check if THIS bot's delivery alone completes the order."""
        bot_active = self.bot_carried_active[bot["id"]]
        for item_type, still_need in self.active_needed.items():
            if still_need > 0 and bot_active.get(item_type, 0) < still_need:
                return False
        return True

    def _compute_bot_assignments(self) -> None:
        """Pre-assign active items to bots (multi-bot optimization)."""
        self.bot_assignments: dict[int, list[dict[str, Any]]] = {}
        if not self.cfg.multi_bot or not self.net_active:
            return

        candidates: list[dict[str, Any]] = []
        seen_types: dict[str, int] = {}
        for it, _ in self._iter_needed_items(self.net_active):
            t = it["type"]
            if seen_types.get(t, 0) >= self.net_active[t]:
                continue
            ipos = tuple(it["position"])
            if not self.gs.adj_cache.get(ipos):
                continue
            candidates.append(it)
            seen_types[t] = seen_types.get(t, 0) + 1

        assignable: list[tuple[int, tuple[int, int], int]] = []
        for b in self.bots:
            if self._is_delivering(b):
                continue
            slots = min(MAX_INVENTORY - len(b["inventory"]), self.max_claim)
            if slots > 0:
                assignable.append((b["id"], tuple(b["position"]), slots))

        if not assignable or not candidates:
            return

        map_width: int = self.full_state["grid"]["width"]
        # Zone penalties spread bots across aisles. Scale zones with team size:
        # 8+ bots: enough zones to avoid convergence (at least 2)
        # 5-7 bots: moderate zones
        # <5 bots: no zones needed
        num_zones = self.cfg.num_zones(len(assignable))
        zone_width: float | None = (map_width / num_zones) if num_zones > 1 else None

        drop_off = self._nearest_dropoff(assignable[0][1]) if self.cfg.use_dropoff_weight else None
        max_slots = max(s for _, _, s in assignable)
        if max_slots == 1 or len(assignable) >= len(candidates):
            self.bot_assignments = self.gs.assign_items_to_bots(
                assignable,
                candidates,
                zone_width=zone_width,
                drop_off=drop_off,
            )
        else:
            self._greedy_assign(assignable, candidates, zone_width, drop_off)
        taken_items: set[str] = {
            it["id"] for items in self.bot_assignments.values() for it in items
        }

        self._stagger_aisle_assignments(assignable, candidates, taken_items)

    def _greedy_assign(
        self,
        assignable: list[tuple[int, tuple[int, int], int]],
        candidates: list[dict[str, Any]],
        zone_width: float | None,
        drop_off: tuple[int, int] | None = None,
    ) -> None:
        """Greedy distance-sorted assignment supporting multi-slot bots."""
        n_bots = len(assignable)
        n_items = len(candidates)
        pairs: list[tuple[float, int, int]] = []
        for bi, (_, bot_pos, _) in enumerate(assignable):
            bot_zone = int(bot_pos[0] / zone_width) if zone_width else 0
            for ii, it in enumerate(candidates):
                _, d = self.gs.find_best_item_target(bot_pos, it)
                if drop_off is not None:
                    ix, iy = it["position"]
                    dx, dy = drop_off
                    d += (abs(ix - dx) + abs(iy - dy)) * ASSIGNMENT_DROPOFF_WEIGHT
                if zone_width:
                    item_zone = int(it["position"][0] / zone_width)
                    d += abs(bot_zone - item_zone) * ZONE_CROSS_PENALTY
                # Tiny tie-breaker: encourage bot i to prefer item i's region
                # so symmetric spawn positions don't all pick the same target.
                if n_bots > 1 and n_items > 1:
                    d += 0.01 * abs(bi / n_bots - ii / n_items)
                pairs.append((d, bi, ii))
        pairs.sort()

        bot_counts: dict[int, int] = {}
        taken: set[int] = set()
        for _d, bi, ii in pairs:
            bot_id, _, slots = assignable[bi]
            if bot_counts.get(bi, 0) >= slots or ii in taken:
                continue
            taken.add(ii)
            bot_counts[bi] = bot_counts.get(bi, 0) + 1
            self.bot_assignments.setdefault(bot_id, []).append(candidates[ii])

    def _stagger_aisle_assignments(
        self,
        assignable: list[tuple[int, tuple[int, int], int]],
        candidates: list[dict[str, Any]],
        taken_items: set[str],
    ) -> None:
        """If 2+ bots target items in the same aisle column, reassign the furthest."""
        if len(self.bot_assignments) < 2:
            return

        bot_columns: dict[int, set[int]] = {}
        for bid, items in self.bot_assignments.items():
            cols: set[int] = set()
            for it in items:
                cols.add(it["position"][0])
            bot_columns[bid] = cols

        col_bots: dict[int, list[tuple[int, float]]] = {}
        for bid, cols in bot_columns.items():
            bot_pos: tuple[int, int] | None = None
            for b_id, b_pos, _ in assignable:
                if b_id == bid:
                    bot_pos = b_pos
                    break
            if bot_pos is None:
                continue
            for col in cols:
                d = abs(bot_pos[0] - col)
                col_bots.setdefault(col, []).append((bid, d))

        for col, bots_in_col in col_bots.items():
            if len(bots_in_col) < 2:
                continue

            bots_in_col.sort(key=lambda x: (x[1], -x[0]), reverse=True)
            furthest_bid = bots_in_col[0][0]

            current_items = self.bot_assignments.get(furthest_bid, [])
            items_in_col = [it for it in current_items if it["position"][0] == col]

            if not items_in_col:
                continue

            for old_item in items_in_col:
                old_type = old_item["type"]
                best_alt: dict[str, Any] | None = None
                best_alt_d = float("inf")
                bot_pos = None
                for b_id, b_pos, _ in assignable:
                    if b_id == furthest_bid:
                        bot_pos = b_pos
                        break
                if bot_pos is None:
                    continue

                for cand in candidates:
                    if cand["id"] in taken_items and cand["id"] != old_item["id"]:
                        continue
                    if cand["type"] != old_type:
                        continue
                    if cand["position"][0] == col:
                        continue
                    _, d = self.gs.find_best_item_target(bot_pos, cand)
                    if d < best_alt_d:
                        best_alt_d = d
                        best_alt = cand

                if best_alt is not None:
                    self.bot_assignments[furthest_bid] = [
                        it
                        for it in self.bot_assignments[furthest_bid]
                        if it["id"] != old_item["id"]
                    ]
                    self.bot_assignments[furthest_bid].append(best_alt)
                    taken_items.discard(old_item["id"])
                    taken_items.add(best_alt["id"])
                    break

    def _identify_batch_b(self) -> None:
        """Identify Batch B: unassigned, non-delivering bots for wave preview pickup."""
        if not self.wave_mode or not self.net_preview:
            self.batch_b_bots = set()
            return
        self.batch_b_bots = {
            b["id"]
            for b in self.bots
            if b["id"] not in self.bot_assignments and not self._is_delivering(b)
        }

    def _bot_urgency(self, b: dict[str, Any]) -> int:
        has_ai = self.bot_has_active[b["id"]]
        n = len(b["inventory"])
        if has_ai and n >= MAX_INVENTORY:
            return 0
        if has_ai and self.active_on_shelves == 0:
            return 1
        if has_ai:
            return 2
        if n == 0:
            return 3
        return 4
