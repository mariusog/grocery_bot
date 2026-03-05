"""RoundPlanner — per-round decision orchestration for all bots."""

from pathfinding import DIRECTIONS, bfs, direction_to, get_needed_items, _predict_pos


class RoundPlanner:
    """Plans actions for all bots in a single round.

    Encapsulates per-round mutable state (claims, predictions, net needs)
    and provides reusable methods for common item search patterns.
    """

    def __init__(self, gs, state):
        self.gs = gs
        self.bots = state["bots"]
        self.items = state["items"]
        self.orders = state["orders"]
        self.drop_off = tuple(state["drop_off"])
        self.rounds_left = state["max_rounds"] - state["round"]
        self.endgame = self.rounds_left <= 30

        # Precomputed lookups
        self.bots_by_id = {b["id"]: b for b in self.bots}
        self.items_at_pos = {}
        for it in self.items:
            p = tuple(it["position"])
            self.items_at_pos.setdefault(p, []).append(it)

        # Per-round mutable state
        self.actions = []
        self.predicted = {}  # bot_id -> predicted (x, y)
        self.claimed = set()  # item IDs claimed this round
        self._yield_to = set()  # positions of higher-urgency bots to avoid

    def plan(self):
        """Main entry: return list of action dicts for all bots."""
        self._detect_pickup_failures()

        if self.gs.blocked_static is None:
            self.gs.init_static(
                {"grid": self._state_grid(), "items": self.items}
            )

        self.active = next(
            (o for o in self.orders
             if o.get("status") == "active" and not o["complete"]),
            None,
        )
        self.preview = next(
            (o for o in self.orders if o.get("status") == "preview"), None
        )

        if not self.active:
            return [{"bot": b["id"], "action": "wait"} for b in self.bots]

        self._compute_needs()
        self._compute_bot_assignments()

        urgency = {b["id"]: self._bot_urgency(b) for b in self.bots}

        for bot in self.bots:
            bid = bot["id"]
            # Build yield set: positions of higher-urgency unprocessed bots
            self._yield_to = set()
            for b in self.bots:
                if b["id"] == bid or b["id"] in self.predicted:
                    continue
                if urgency[b["id"]] < urgency[bid]:
                    self._yield_to.add(tuple(b["position"]))

            self._decide_bot(bot)

        return self.actions

    def _state_grid(self):
        """Extract grid from the state for init_static compatibility."""
        return self._full_state["grid"]

    # ------------------------------------------------------------------
    # Initialization helpers
    # ------------------------------------------------------------------

    def _detect_pickup_failures(self):
        gs = self.gs
        for b in self.bots:
            bid = b["id"]
            if bid not in gs.last_pickup:
                continue
            last_item_id, last_inv_len = gs.last_pickup[bid]
            if len(b["inventory"]) <= last_inv_len:
                gs.pickup_fail_count[last_item_id] = (
                    gs.pickup_fail_count.get(last_item_id, 0) + 1
                )
                if gs.pickup_fail_count[last_item_id] >= 3:
                    gs.blacklisted_items.add(last_item_id)
            else:
                gs.pickup_fail_count.pop(last_item_id, None)
            del gs.last_pickup[bid]

    def _compute_needs(self):
        self.active_needed = get_needed_items(self.active)
        preview_needed = get_needed_items(self.preview) if self.preview else {}

        self.items_by_type = {}
        for it in self.items:
            self.items_by_type.setdefault(it["type"], []).append(it)

        # Track what's already carried (single pass over all inventories)
        carried_active = {}
        carried_preview = {}
        self.bot_has_active = {}
        # Per-bot carried active items (for order-completion check)
        self.bot_carried_active = {}
        for bot in self.bots:
            has = False
            bot_active = {}
            for inv_item in bot["inventory"]:
                if self.active_needed.get(inv_item, 0) > 0:
                    carried_active[inv_item] = carried_active.get(inv_item, 0) + 1
                    bot_active[inv_item] = bot_active.get(inv_item, 0) + 1
                    has = True
                elif inv_item in preview_needed:
                    carried_preview[inv_item] = carried_preview.get(inv_item, 0) + 1
            self.bot_has_active[bot["id"]] = has
            self.bot_carried_active[bot["id"]] = bot_active

        self.net_active = {
            t: c - carried_active.get(t, 0)
            for t, c in self.active_needed.items()
            if c - carried_active.get(t, 0) > 0
        }
        self.active_on_shelves = sum(self.net_active.values())

        self.net_preview = {
            t: c - carried_preview.get(t, 0)
            for t, c in preview_needed.items()
            if c - carried_preview.get(t, 0) > 0
        }
        self.active_types = set(self.active_needed.keys())
        self.order_nearly_complete = 0 < self.active_on_shelves <= 2

        # Fair item distribution
        idle_bots = sum(
            1 for bot in self.bots
            if not self._is_delivering(bot)
        )
        total = self.active_on_shelves
        self.max_claim = (
            max(1, (total + idle_bots - 1) // idle_bots) if idle_bots > 0 else 3
        )

        # Dedicated preview bot assignment (Phase 2.2)
        # Only for exactly 2 bots; more bots benefit more from all focusing on active
        self.preview_bot_id = None
        if (self.order_nearly_complete and len(self.bots) == 2
                and self.preview and self.net_preview):
            self._assign_preview_bot()

    def _is_delivering(self, bot):
        """True if bot is busy delivering (shouldn't count as idle)."""
        has_ai = self.bot_has_active[bot["id"]]
        if has_ai and (len(bot["inventory"]) >= 3 or self.active_on_shelves == 0):
            return True
        if has_ai and tuple(bot["position"]) == self.drop_off:
            return True
        return False

    def _assign_preview_bot(self):
        """Assign the bot furthest from remaining active items as preview-only bot.

        Only assigns when there are more idle bots than active items on shelves,
        so pulling one bot away doesn't leave active items unattended.
        """
        # Count bots that could pick active items (idle, no active in inv)
        idle_for_active = []
        for bot in self.bots:
            if self._is_delivering(bot):
                continue
            idle_for_active.append(bot)

        # Only dedicate a preview bot if we have MORE idle bots than active
        # items on shelves (i.e., at least one bot is redundant)
        if len(idle_for_active) <= self.active_on_shelves:
            return

        # Find positions of remaining active items on shelves
        active_item_positions = []
        for it, _ in self._iter_needed_items(self.net_active):
            cell, _ = self.gs.find_best_item_target(self.drop_off, it)
            if cell:
                active_item_positions.append(cell)
        if not active_item_positions:
            return

        # Center of mass of active items (using walkable positions)
        cx = sum(p[0] for p in active_item_positions) / len(active_item_positions)
        cy = sum(p[1] for p in active_item_positions) / len(active_item_positions)

        # Find idle bot furthest from active items center that has no active items
        best_bid = None
        best_dist = -1
        for bot in idle_for_active:
            if self.bot_has_active[bot["id"]]:
                continue  # don't pull a bot that has active items
            bx, by = bot["position"]
            d = abs(bx - cx) + abs(by - cy)
            if d > best_dist:
                best_dist = d
                best_bid = bot["id"]

        if best_bid is not None:
            self.preview_bot_id = best_bid

    def _bot_delivery_completes_order(self, bot):
        """Check if THIS bot's delivery alone completes the order.

        True if for every item type still needed, this bot carries enough.
        active_needed is already {type: still_needed_count}.
        """
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

        # Collect candidate items (up to needed count per type)
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

        # Find assignable bots (have inventory space, not rushing to deliver)
        assignable = []
        for b in self.bots:
            if self._is_delivering(b):
                continue
            slots = min(3 - len(b["inventory"]), self.max_claim)
            if slots > 0:
                assignable.append((b["id"], tuple(b["position"]), slots))

        if not assignable or not candidates:
            return

        # Zone-based penalty for 5+ bots to reduce cross-traffic
        map_width = self._full_state["grid"]["width"]
        num_zones = max(1, len(assignable) // 2) if len(self.bots) >= 5 else 1
        zone_width = map_width / num_zones if num_zones > 1 else map_width

        # Build (cost, bot_idx, item_idx) pairs
        pairs = []
        for bi, (_, bot_pos, _) in enumerate(assignable):
            bot_zone = int(bot_pos[0] / zone_width) if num_zones > 1 else 0
            for ii, it in enumerate(candidates):
                _, d = self.gs.find_best_item_target(bot_pos, it)
                if num_zones > 1:
                    item_zone = int(it["position"][0] / zone_width)
                    d += abs(bot_zone - item_zone) * 3
                pairs.append((d, bi, ii))
        pairs.sort()

        # Greedy assignment: shortest distance first
        bot_counts = {}
        taken_items = set()
        for d, bi, ii in pairs:
            bot_id, _, slots = assignable[bi]
            if bot_counts.get(bi, 0) >= slots or ii in taken_items:
                continue
            taken_items.add(ii)
            bot_counts[bi] = bot_counts.get(bi, 0) + 1
            self.bot_assignments.setdefault(bot_id, []).append(candidates[ii])

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

    # ------------------------------------------------------------------
    # Per-bot decision (steps 1-7)
    # ------------------------------------------------------------------

    def _decide_bot(self, bot):
        bid = bot["id"]
        bx, by = bot["position"]
        pos = (bx, by)
        inv = bot["inventory"]
        blocked = self._build_blocked(bid)
        has_active = self.bot_has_active[bid]

        # Phase 2.2: dedicated preview bot skips active items entirely
        if bid == self.preview_bot_id and not has_active:
            if self._try_preview_prepick(bid, bx, by, pos, inv, blocked):
                return
            if self._try_clear_dropoff(bid, bx, by, pos, blocked):
                return
            self._emit(bid, bx, by, {"bot": bid, "action": "wait"})
            return

        # Step 1: at drop-off with active items -> deliver
        if pos == self.drop_off and has_active:
            self._emit(bid, bx, by, {"bot": bid, "action": "drop_off"})
            return

        # Phase 4.4: deliver partial items if it COMPLETES the order (+5 bonus)
        # This triggers when items are still on shelves but this bot's inventory
        # alone can finish the order (already delivered + this bot's items = required)
        if (has_active and self.active_on_shelves > 0
                and len(inv) < 3
                and self._bot_delivery_completes_order(bot)):
            # Rush to deliver — completing order is worth +5 bonus
            self._emit_move_or_wait(bid, bx, by, pos, self.drop_off, blocked)
            return

        # Step 2: all active items picked up -> rush to deliver
        if has_active and self.active_on_shelves == 0:
            if self.preview and len(inv) < 3:
                # Try grabbing a preview item on the way
                adj = self._find_adjacent_needed(
                    bx, by, self.net_preview, prefer_cascade=True
                )
                if adj:
                    self._claim(adj, self.net_preview)
                    self._emit(bid, bx, by, self._pickup(bid, adj))
                    return
                item, cell = self._find_detour_item(
                    pos, self.net_preview, prefer_cascade=True
                )
                if item:
                    self._claim(item, self.net_preview)
                    if self._emit_move(bid, bx, by, pos, cell, blocked):
                        return
            self._emit_move_or_wait(bid, bx, by, pos, self.drop_off, blocked)
            return

        # Step 3: opportunistic adjacent preview pickup (spare slots only)
        if self.preview and self._spare_slots(inv) > 0:
            adj = self._find_adjacent_needed(
                bx, by, self.net_preview, prefer_cascade=True
            )
            if adj:
                self._claim(adj, self.net_preview)
                self._emit(bid, bx, by, self._pickup(bid, adj))
                return

        # Step 3b: inventory full -> deliver
        if has_active and len(inv) >= 3:
            self._emit_move_or_wait(bid, bx, by, pos, self.drop_off, blocked)
            return

        # Phase 4.4: zero-cost delivery — deliver if adjacent to dropoff
        # and have active items, en route to next pickup (don't detour)
        if (has_active and pos != self.drop_off
                and self.gs.dist_static(pos, self.drop_off) == 1
                and not self._bot_delivery_completes_order(bot)):
            # Check if delivering now is "free" — next item is further from dropoff
            # Only deliver if it doesn't cost extra rounds vs going straight to item
            next_item_pos = self._find_nearest_active_item_pos(pos)
            if next_item_pos is not None:
                dist_via_dropoff = 1 + self.gs.dist_static(self.drop_off, next_item_pos)
                dist_direct = self.gs.dist_static(pos, next_item_pos)
                if dist_via_dropoff <= dist_direct + 1:
                    # Zero or near-zero cost: deliver on the way
                    self._emit_move_or_wait(
                        bid, bx, by, pos, self.drop_off, blocked
                    )
                    return

        # Phase 4.3: improved end-game strategy
        if self.endgame and inv:
            d = self.gs.dist_static(pos, self.drop_off)
            if d + 1 >= self.rounds_left:
                # Must deliver now or lose items
                self._emit_move_or_wait(bid, bx, by, pos, self.drop_off, blocked)
                return
            # Calculate if we can complete the order in remaining rounds
            if has_active and self.active_on_shelves > 0:
                rounds_to_complete = self._estimate_rounds_to_complete(pos, inv)
                if rounds_to_complete > self.rounds_left:
                    # Can't complete order — maximize individual item deliveries
                    if self._try_maximize_items(bid, bx, by, pos, inv, blocked):
                        return

        # Step 4: pick up active items (adjacent first, then TSP route)
        if self._try_active_pickup(bid, bx, by, pos, inv, blocked):
            return

        # Step 5: deliver active items (with optional preview detour)
        if has_active:
            spare = self._spare_slots(inv)
            if self.preview and spare > 0 and not self.order_nearly_complete:
                item, cell = self._find_detour_item(pos, self.net_preview)
                if item:
                    self._claim(item, self.net_preview)
                    if self._emit_move(bid, bx, by, pos, cell, blocked):
                        return
            self._emit_move_or_wait(bid, bx, by, pos, self.drop_off, blocked)
            return

        # Step 6: pre-pick preview items
        if self._try_preview_prepick(bid, bx, by, pos, inv, blocked):
            return

        # Step 7: clear dropoff area or move out of others' way when idle
        if self._try_clear_dropoff(bid, bx, by, pos, blocked):
            return

        # Step 8: idle bot at spawn or blocking — move to a less crowded spot
        if len(self.bots) > 1:
            if self._try_move_away_from_crowd(bid, bx, by, pos, blocked):
                return

        self._emit(bid, bx, by, {"bot": bid, "action": "wait"})

    # ------------------------------------------------------------------
    # Reusable item search helpers
    # ------------------------------------------------------------------

    def _is_available(self, item):
        """True if item is not claimed or blacklisted."""
        return item["id"] not in self.claimed and item["id"] not in self.gs.blacklisted_items

    def _iter_needed_items(self, needed):
        """Yield (item, is_cascade) for available items matching needed dict."""
        for item_type, count in needed.items():
            if count <= 0:
                continue
            is_cascade = item_type not in self.active_types
            for it in self.items_by_type.get(item_type, []):
                if self._is_available(it):
                    yield it, is_cascade

    def _find_adjacent_needed(self, bx, by, needed, prefer_cascade=False):
        """Find best needed item adjacent to (bx, by) using position lookup.

        When prefer_cascade is True, prefers items whose type is NOT in the
        active order (they survive cascade delivery).
        """
        best = None
        best_cascade = False
        for dx, dy in DIRECTIONS:
            for it in self.items_at_pos.get((bx + dx, by + dy), []):
                if not self._is_available(it):
                    continue
                if needed.get(it["type"], 0) <= 0:
                    continue
                is_cascade = prefer_cascade and it["type"] not in self.active_types
                if is_cascade and not best_cascade:
                    best, best_cascade = it, True
                elif not best:
                    best = it
        return best

    def _find_detour_item(self, pos, needed, max_detour=3, prefer_cascade=False):
        """Find item worth detouring for on the way to drop-off.

        Returns (item, target_cell) or (None, None).
        """
        direct = self.gs.dist_static(pos, self.drop_off)
        best_item = best_cell = None
        best_cost = float("inf")
        best_cascade = False

        for it, is_cascade in self._iter_needed_items(needed):
            if not prefer_cascade:
                is_cascade = False
            cell, d = self.gs.find_best_item_target(pos, it)
            if not cell:
                continue
            detour = d + self.gs.dist_static(cell, self.drop_off) - direct
            if is_cascade and not best_cascade:
                best_cost = detour
                best_item, best_cell, best_cascade = it, cell, True
            elif is_cascade == best_cascade and detour < best_cost:
                best_cost = detour
                best_item, best_cell = it, cell

        effective_max = (6 if best_cascade else max_detour) if prefer_cascade else max_detour
        if best_item and best_cost <= effective_max:
            return best_item, best_cell
        return None, None

    # ------------------------------------------------------------------
    # Phase 4.3: end-game helpers
    # ------------------------------------------------------------------

    def _find_nearest_active_item_pos(self, pos):
        """Find the position of the nearest reachable active item on shelves."""
        best_cell = None
        best_d = float("inf")
        for it, _ in self._iter_needed_items(self.net_active):
            cell, d = self.gs.find_best_item_target(pos, it)
            if cell and d < best_d:
                best_d = d
                best_cell = cell
        return best_cell

    def _estimate_rounds_to_complete(self, pos, inv):
        """Estimate rounds needed to pick up all remaining active items and deliver."""
        # Collect remaining items to pick
        remaining = []
        for it, _ in self._iter_needed_items(self.net_active):
            cell, d = self.gs.find_best_item_target(pos, it)
            if cell and d < float("inf"):
                remaining.append((it, cell, d))
        if not remaining:
            # Only need to deliver what we have
            return self.gs.dist_static(pos, self.drop_off) + 1

        # Estimate: greedy nearest-neighbor tour + delivery trips
        remaining.sort(key=lambda c: c[2])
        total_dist = 0
        current = pos
        picked = 0
        for it, cell, _ in remaining:
            d = self.gs.dist_static(current, cell)
            total_dist += d + 1  # +1 for pickup
            current = cell
            picked += 1
            if picked + len(inv) >= 3:
                # Need a delivery trip
                total_dist += self.gs.dist_static(current, self.drop_off) + 1
                current = self.drop_off
                picked = 0
        # Final delivery
        if picked > 0 or inv:
            total_dist += self.gs.dist_static(current, self.drop_off) + 1
        return total_dist

    def _try_maximize_items(self, bid, bx, by, pos, inv, blocked):
        """End-game: maximize individual item deliveries when order can't complete.

        Pick up nearby items that can be delivered before time runs out.
        If carrying items, decide whether to deliver now or grab one more.
        """
        has_active = self.bot_has_active[bid]
        d_to_drop = self.gs.dist_static(pos, self.drop_off)

        # If carrying items, check if we should deliver now
        if has_active and len(inv) > 0:
            # Can we grab one more and still deliver?
            nearest = self._find_nearest_active_item_pos(pos)
            if nearest:
                d_to_item = self.gs.dist_static(pos, nearest)
                d_item_to_drop = self.gs.dist_static(nearest, self.drop_off)
                total_with_pickup = d_to_item + 1 + d_item_to_drop + 1
                if total_with_pickup < self.rounds_left and len(inv) < 3:
                    # Worth picking up one more
                    return False  # Fall through to normal pickup

            # Deliver what we have
            self._emit_move_or_wait(bid, bx, by, pos, self.drop_off, blocked)
            return True

        return False

    # ------------------------------------------------------------------
    # Step 4: active item pickup
    # ------------------------------------------------------------------

    def _try_active_pickup(self, bid, bx, by, pos, inv, blocked):
        """Pick up adjacent active items, or navigate via TSP route."""
        # Adjacent pickup via position lookup (zero cost - always take it)
        if len(inv) < 3:
            for dx, dy in DIRECTIONS:
                for it in self.items_at_pos.get((bx + dx, by + dy), []):
                    if not self._is_available(it):
                        continue
                    if self.net_active.get(it["type"], 0) <= 0:
                        continue
                    self._claim(it, self.net_active)
                    self._emit(bid, bx, by, self._pickup(bid, it))
                    return True

        if len(inv) >= 3:
            return False

        # Pre-assigned route (multi-bot optimization)
        if bid in self.bot_assignments:
            route = self._build_assigned_route(bid, pos)
            if route:
                for it, _ in route:
                    self._claim(it, self.net_active)
                if self._emit_move(bid, bx, by, pos, route[0][1], blocked):
                    return True

        # Greedy fallback: find reachable items and plan TSP route
        route = self._build_greedy_route(pos, inv)
        if route:
            for it, _ in route:
                self._claim(it, self.net_active)
            if self._emit_move(bid, bx, by, pos, route[0][1], blocked):
                return True

        return False

    def _build_assigned_route(self, bid, pos):
        assigned = []
        for it in self.bot_assignments[bid]:
            if it["id"] in self.claimed:
                continue
            cell, d = self.gs.find_best_item_target(pos, it)
            if cell and d < float("inf"):
                assigned.append((it, cell))
        if assigned:
            return self.gs.tsp_route(pos, assigned, self.drop_off)
        return None

    def _build_greedy_route(self, pos, inv):
        candidates = []
        for it, _ in self._iter_needed_items(self.net_active):
            cell, d = self.gs.find_best_item_target(pos, it)
            if not cell or d == float("inf"):
                continue
            round_trip = d + 1 + self.gs.dist_static(cell, self.drop_off)
            if round_trip < self.rounds_left:
                candidates.append((it, cell, d))

        if not candidates:
            return None

        # Phase 4.2: Item proximity clustering
        # When multiple same-type items exist, prefer ones closer to other
        # needed items (center-of-mass tiebreaker)
        if len(candidates) > 1:
            candidates = self._cluster_select(candidates)

        slots = min(3 - len(inv), self.max_claim)

        # Select best item per type, up to what's still needed
        selected = []
        selected_types = {}
        for it, cell, d in candidates:
            t = it["type"]
            still_needed = self.net_active.get(t, 0) - selected_types.get(t, 0)
            if still_needed > 0:
                selected.append((it, cell))
                selected_types[t] = selected_types.get(t, 0) + 1

        if not selected:
            return None
        if len(selected) > slots:
            return self.gs.plan_multi_trip(pos, selected, self.drop_off, slots)
        return self.gs.tsp_route(pos, selected, self.drop_off)

    def _cluster_select(self, candidates):
        """For same-type items, prefer the one closest to other needed items.

        Uses center-of-mass of all candidate positions as a gravity point.
        Re-ranks candidates by: distance_to_bot + cluster_penalty.
        """
        # Compute center of mass of ALL needed item positions
        all_positions = [cell for _, cell, _ in candidates]
        if len(all_positions) < 2:
            return candidates
        cx = sum(p[0] for p in all_positions) / len(all_positions)
        cy = sum(p[1] for p in all_positions) / len(all_positions)

        # Group candidates by type
        by_type = {}
        for entry in candidates:
            t = entry[0]["type"]
            by_type.setdefault(t, []).append(entry)

        result = []
        for t, entries in by_type.items():
            needed = self.net_active.get(t, 0)
            if len(entries) <= needed:
                # Need all of them — keep sorted by distance to bot
                entries.sort(key=lambda e: e[2])
                result.extend(entries)
            else:
                # More available than needed — pick ones closest to center
                # Score: bot_distance + 0.5 * distance_from_center
                scored = []
                for entry in entries:
                    _, cell, d = entry
                    cluster_d = abs(cell[0] - cx) + abs(cell[1] - cy)
                    scored.append((*entry, d + 0.5 * cluster_d))
                scored.sort(key=lambda e: e[3])
                result.extend((it, cell, d) for it, cell, d, _ in scored)

        # Re-sort by bot distance for final ordering
        result.sort(key=lambda c: c[2])
        return result

    # ------------------------------------------------------------------
    # Step 6: preview pre-pick
    # ------------------------------------------------------------------

    def _try_preview_prepick(self, bid, bx, by, pos, inv, blocked):
        if not self.preview or self._spare_slots(inv) <= 0:
            return False

        is_preview_bot = (bid == self.preview_bot_id)

        # Pass 1: check adjacent items via position lookup (free pickup)
        adj = self._find_adjacent_needed(bx, by, self.net_preview, prefer_cascade=True)
        if adj:
            self._claim(adj, self.net_preview)
            self._emit(bid, bx, by, self._pickup(bid, adj))
            return True

        # Pass 2: walk to distant preview items
        # Normal bots only do this when no active items left on shelves
        # Preview bots always do this (that's their job)
        if not is_preview_bot and self.active_on_shelves > 0:
            return False

        best = None
        best_dist = float("inf")
        best_cascade = False
        for it, is_cascade in self._iter_needed_items(self.net_preview):
            _, d = self.gs.find_best_item_target(pos, it)
            if is_cascade and not best_cascade:
                best, best_dist, best_cascade = it, d, True
            elif is_cascade == best_cascade and d < best_dist:
                best, best_dist = it, d

        if not best:
            return False

        self._claim(best, self.net_preview)
        target, _ = self.gs.find_best_item_target(pos, best)
        if target:
            return self._emit_move(bid, bx, by, pos, target, blocked)
        return False

    # ------------------------------------------------------------------
    # Step 7: clear dropoff area
    # ------------------------------------------------------------------

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

    def _try_move_away_from_crowd(self, bid, bx, by, pos, blocked):
        """Idle bot moves toward less crowded area to avoid blocking others."""
        # Count nearby bots (within Manhattan distance 2)
        nearby = sum(
            1 for b in self.bots
            if b["id"] != bid
            and abs(b["position"][0] - bx) + abs(b["position"][1] - by) <= 2
        )
        if nearby == 0:
            return False
        # Move to the neighbor with fewest adjacent bots
        best = None
        best_crowd = nearby
        for dx, dy in DIRECTIONS:
            npos = (bx + dx, by + dy)
            if npos in blocked:
                continue
            crowd = sum(
                1 for b in self.bots
                if b["id"] != bid
                and abs(b["position"][0] - npos[0]) + abs(b["position"][1] - npos[1]) <= 2
            )
            if crowd < best_crowd:
                best_crowd = crowd
                best = npos
        if best:
            self._emit(
                bid, bx, by,
                {"bot": bid, "action": direction_to(bx, by, best[0], best[1])},
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Action emission and collision avoidance
    # ------------------------------------------------------------------

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

    def _emit_move(self, bid, bx, by, pos, target, blocked):
        """BFS to target and emit. Returns True if a move was emitted."""
        next_pos = bfs(pos, target, blocked)
        if next_pos and next_pos in blocked:
            next_pos = None
        if next_pos:
            self._emit(
                bid, bx, by,
                {"bot": bid, "action": direction_to(bx, by, next_pos[0], next_pos[1])},
            )
            return True
        return False

    def _emit_move_or_wait(self, bid, bx, by, pos, target, blocked):
        """Move toward target with unstick fallback, or wait."""
        next_pos = bfs(pos, target, blocked)
        # BFS may return a position that's blocked (goal occupied by another bot)
        if next_pos and next_pos in blocked:
            next_pos = None
        if not next_pos:
            # Unstick: try any unblocked neighbor
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
        """Build blocked set for a specific bot (static + other bots)."""
        other = {
            self.predicted.get(b["id"], tuple(b["position"]))
            for b in self.bots if b["id"] != bid
        }
        return self.gs.blocked_static | other

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------

    def _spare_slots(self, inv):
        return (3 - len(inv)) - self.active_on_shelves

    def _claim(self, item, needed_dict):
        self.claimed.add(item["id"])
        needed_dict[item["type"]] = needed_dict.get(item["type"], 0) - 1

    @staticmethod
    def _pickup(bid, item):
        return {"bot": bid, "action": "pick_up", "item_id": item["id"]}
