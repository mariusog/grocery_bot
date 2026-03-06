"""Bot-to-item assignment logic for RoundPlanner."""


class AssignmentMixin:
    """Mixin providing bot assignment, preview bot selection, and urgency."""

    def _is_delivering(self, bot):
        """True if bot is busy delivering (shouldn't count as idle)."""
        has_ai = self.bot_has_active[bot["id"]]
        if has_ai and (len(bot["inventory"]) >= 3 or self.active_on_shelves == 0):
            return True
        if has_ai and tuple(bot["position"]) == self.drop_off:
            return True
        return False

    def _assign_preview_bot(self):
        """Assign bots furthest from remaining active items as preview-only bots.

        For 2+ bots, allow up to (num_idle - active_on_shelves - 1) preview bots,
        keeping at least 1 more idle bot than needed for active items.
        """
        idle_for_active = []
        for bot in self.bots:
            if self._is_delivering(bot):
                continue
            idle_for_active.append(bot)

        if len(idle_for_active) <= self.active_on_shelves:
            return

        active_item_positions = []
        for it, _ in self._iter_needed_items(self.net_active):
            cell, _ = self.gs.find_best_item_target(self.drop_off, it)
            if cell:
                active_item_positions.append(cell)
        if not active_item_positions:
            return

        cx = sum(p[0] for p in active_item_positions) / len(active_item_positions)
        cy = sum(p[1] for p in active_item_positions) / len(active_item_positions)

        surplus = len(idle_for_active) - self.active_on_shelves
        if surplus <= 0:
            return
        max_preview = max(1, surplus - 1) if len(self.bots) >= 5 else 1

        candidates = []
        for bot in idle_for_active:
            if self.bot_has_active[bot["id"]]:
                continue
            if len(bot["inventory"]) >= 3:
                continue
            bx, by = bot["position"]
            d = abs(bx - cx) + abs(by - cy)
            candidates.append((d, bot["id"]))

        candidates.sort(reverse=True)

        for i, (_, bid) in enumerate(candidates):
            if i >= max_preview:
                break
            self.preview_bot_ids.add(bid)

        if len(self.preview_bot_ids) == 1:
            self.preview_bot_id = next(iter(self.preview_bot_ids))
        elif self.preview_bot_ids:
            self.preview_bot_id = next(iter(self.preview_bot_ids))

    def _bot_delivery_completes_order(self, bot):
        """Check if THIS bot's delivery alone completes the order."""
        bot_active = self.bot_carried_active[bot["id"]]
        for item_type, still_need in self.active_needed.items():
            if still_need > 0 and bot_active.get(item_type, 0) < still_need:
                return False
        return True

    def _compute_bot_assignments(self):
        """Pre-assign active items to bots (multi-bot optimization)."""
        self.bot_assignments = {}
        if len(self.bots) <= 1 or not self.net_active:
            return

        candidates = []
        seen_types = {}
        for it, _ in self._iter_needed_items(self.net_active):
            t = it["type"]
            if seen_types.get(t, 0) >= self.net_active[t]:
                continue
            ipos = tuple(it["position"])
            if not self.gs.adj_cache.get(ipos):
                continue
            candidates.append(it)
            seen_types[t] = seen_types.get(t, 0) + 1

        assignable = []
        for b in self.bots:
            if self._is_delivering(b):
                continue
            slots = min(3 - len(b["inventory"]), self.max_claim)
            if slots > 0:
                assignable.append((b["id"], tuple(b["position"]), slots))

        if not assignable or not candidates:
            return

        map_width = self._full_state["grid"]["width"]
        num_zones = max(1, len(assignable) // 2) if len(self.bots) >= 5 else 1
        zone_width = (map_width / num_zones) if num_zones > 1 else None

        max_slots = max(s for _, _, s in assignable)
        if max_slots == 1 or len(assignable) >= len(candidates):
            self.bot_assignments = self.gs.assign_items_to_bots(
                assignable, candidates, zone_width=zone_width
            )
        else:
            self._greedy_assign(assignable, candidates, zone_width)
        taken_items = {it["id"] for items in self.bot_assignments.values()
                       for it in items}

        self._stagger_aisle_assignments(assignable, candidates, taken_items)

    def _greedy_assign(self, assignable, candidates, zone_width):
        """Greedy distance-sorted assignment supporting multi-slot bots."""
        pairs = []
        for bi, (_, bot_pos, _) in enumerate(assignable):
            bot_zone = int(bot_pos[0] / zone_width) if zone_width else 0
            for ii, it in enumerate(candidates):
                _, d = self.gs.find_best_item_target(bot_pos, it)
                if zone_width:
                    item_zone = int(it["position"][0] / zone_width)
                    d += abs(bot_zone - item_zone) * 3
                pairs.append((d, bi, ii))
        pairs.sort()

        bot_counts = {}
        taken = set()
        for d, bi, ii in pairs:
            bot_id, _, slots = assignable[bi]
            if bot_counts.get(bi, 0) >= slots or ii in taken:
                continue
            taken.add(ii)
            bot_counts[bi] = bot_counts.get(bi, 0) + 1
            self.bot_assignments.setdefault(bot_id, []).append(candidates[ii])

    def _stagger_aisle_assignments(self, assignable, candidates, taken_items):
        """If 2+ bots target items in the same aisle column, reassign the furthest."""
        if len(self.bot_assignments) < 2:
            return

        bot_columns = {}
        for bid, items in self.bot_assignments.items():
            cols = set()
            for it in items:
                cols.add(it["position"][0])
            bot_columns[bid] = cols

        col_bots = {}
        for bid, cols in bot_columns.items():
            bot_pos = None
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

            bots_in_col.sort(key=lambda x: x[1], reverse=True)
            furthest_bid = bots_in_col[0][0]

            current_items = self.bot_assignments.get(furthest_bid, [])
            items_in_col = [it for it in current_items if it["position"][0] == col]

            if not items_in_col:
                continue

            for old_item in items_in_col:
                old_type = old_item["type"]
                best_alt = None
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
                        it for it in self.bot_assignments[furthest_bid]
                        if it["id"] != old_item["id"]
                    ]
                    self.bot_assignments[furthest_bid].append(best_alt)
                    taken_items.discard(old_item["id"])
                    taken_items.add(best_alt["id"])
                    break

    def _bot_urgency(self, b):
        has_ai = self.bot_has_active[b["id"]]
        n = len(b["inventory"])
        if has_ai and n >= 3:
            return 0
        if has_ai and self.active_on_shelves == 0:
            return 1
        if has_ai:
            return 2
        if n == 0:
            return 3
        return 4
