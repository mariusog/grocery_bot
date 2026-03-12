# Plan: 2000 Live Points

## Current State (2026-03-08 maps)

| Difficulty | Bots | Rounds | Our Score | #1 Score | Gap | Theoretical Max |
|------------|------|--------|-----------|----------|-----|-----------------|
| Easy       | 1    | 300    | 116       | ~180?    | ~64 | ~425            |
| Medium     | 3    | 300    | 163       | ~214?    | ~51 | ~450            |
| Hard       | 5    | 300    | 150       | 252      | 102 | ~450            |
| Expert     | 10   | 300    | 105       | 303      | 198 | ~500            |
| Nightmare  | 20   | 500    | 343       | 1026     | 683 | ~1000+          |
| **Total**  |      |        | **877**   | **~2000**| **1123** |            |

Scoring: +1/item delivered, +5/order completed. Items respawn after pickup.

## The Core Problem

Our bot makes **per-round, per-bot greedy decisions**. This fundamentally cannot
scale past ~5 bots. Evidence from Nightmare diagnostics:

- **Bot 18-19: 0 picks, 0 deliveries, 450+ rounds idle** (out of 500)
- **Bot 15-17: 2-5 picks each** (should be 20-30)
- **81.2% waste** — 4/5 pickups are non-active items
- **1.40 items per delivery** — should be 2.5+
- **32 orders in 500 rounds** (15.6 rds/order) — #1 does ~80 orders (6.25 rds/order)
- **367 InvFull waits** — bots stuck with full non-active inventory

Root causes:
1. **Tail bots never get assigned work** — assignment starvation
2. **Preview picking is mostly waste** — 81% waste means speculative picks are wrong
3. **Bots deliver half-empty** — 1.4 items/delivery wastes travel time
4. **Dropoff bottleneck** — single cell, 20 bots queuing
5. **No spatial coordination** — bots converge on same aisles

## Target Scores for 2000

| Difficulty | Current | Target | Needed | Strategy Focus |
|------------|---------|--------|--------|----------------|
| Easy       | 116     | 170    | +54    | Routing, early delivery |
| Medium     | 163     | 230    | +67    | Multi-trip, early delivery |
| Hard       | 150     | 280    | +130   | Assignment, coordination |
| Expert     | 105     | 320    | +215   | Zone ownership, pipeline |
| Nightmare  | 343     | 1000   | +657   | Everything below |
| **Total**  | **877** | **2000**| **+1123** | |

## Architecture Changes (by priority)

### A1: Zone-Based Bot Ownership (Nightmare +200-300, Expert +80-120)

**The single biggest win.** Divide the map into vertical zones, one per bot-group.
Each bot only picks items in its zone. Eliminates convergence and congestion.

**Current**: All 20 bots compete for the same 4-6 active items → 14+ bots idle.
**Target**: 4 zones × 5 bots each. Each zone has a dedicated pickup/delivery pipeline.

```
Zone layout for 30x18 Nightmare:
  Zone 0: cols 1-7   (aisles 0-1) — Bots 0-4
  Zone 1: cols 8-14  (aisles 2-3) — Bots 5-9
  Zone 2: cols 15-21 (aisles 4-5) — Bots 10-14
  Zone 3: cols 22-28 (aisles 6-7) — Bots 15-19
```

Within each zone, bots have roles:
- 2-3 pickers: grab items from shelves
- 1-2 couriers: ferry items to dropoff
- Roles rotate based on inventory state

**Implementation**:
- New file: `planner/zones.py` — ZoneMixin
- Modify `_compute_bot_assignments()` to respect zone boundaries
- Modify idle positioning to keep bots in their zone
- Gate to teams >= 8 (Expert/Nightmare only)

### A2: Smart Preview Strategy (Nightmare +100-200, Expert +30-50)

**Current**: Bots speculatively pick ANY preview item → 81% waste.
**Target**: Only pick preview items that have high probability of matching the
next active order, based on item frequency analysis.

**Approach**: Track which item types appear most frequently across orders.
For the preview order, prioritize picking items that:
1. Appear in BOTH the preview order AND are common across all orders
2. Are adjacent (zero cost) or very close (≤2 steps)
3. Don't fill the last inventory slot (keep 1 slot reserved for active)

For Nightmare with 21 item types and 4-6 items per order, each type appears
in ~25% of orders. Currently we pick everything; we should pick only high-value types.

**Even better**: For large teams, most bots should NOT preview-pick at all.
Only 2-3 designated preview bots should pick, and only cascade-likely items.
The rest should stay mobile and ready for the next active order.

**Implementation**:
- Modify `_step_opportunistic_preview` and `_step_preview_prepick`: skip for
  most bots on large teams
- Add item frequency tracking in `round_planner.py` init
- New constant: `MAX_PREVIEW_BOTS = 3` for teams >= 8
- For non-preview bots: NO speculative pickup at all, just position near items

### A3: Delivery Pipeline (Nightmare +100-150, Expert +40-60)

**Current**: Max 2 bots at dropoff. Others wait with full inventory (367 waits).
**Target**: Staggered delivery — bots arrive at dropoff in sequence, no waiting.

**Approach**:
1. **Delivery scheduling**: When bot finishes picking, compute its ETA to dropoff.
   Schedule it to arrive when the dropoff is free (not simultaneously with others).
2. **Wait-near-dropoff staging**: Bots with full active inventory stage at
   distance 2-3 from dropoff, advance when the current deliverer leaves.
3. **Multi-dropoff exploitation**: If the map has multiple dropoff zones,
   route bots to the least-congested one (already partially implemented).
4. **Delivery batching**: Bots should deliver 3 items, not 1-2. Currently
   avg 1.4 items/delivery. Each trip to dropoff costs ~8-15 rounds of travel.
   Delivering 3 instead of 1.4 nearly doubles throughput.

**Implementation**:
- Enhance `_update_delivery_queue()` in coordination.py with ETA-based scheduling
- Modify `_should_head_to_dropoff()` to require min 2 active items for large teams
- Add staging area logic near dropoff for queued bots

### A4: Fill Before Deliver (All difficulties +10-30 each)

**Current**: Bots with 1 active item rush to deliver. 1.4 avg items/delivery.
**Target**: Bots fill inventory to 2-3 items before delivering, unless:
- Order would be completed (keep +5 bonus rush)
- No more active items on shelves
- Close to dropoff (≤3 steps)
- Endgame (not enough rounds)

**This is `_should_deliver_early()` in reverse** — we need a `_should_fill_up()`.

For an order needing 5 items with 3 bots:
- Current: Each bot picks 1-2, delivers half-empty → 5 deliveries, ~80 rounds
- Target: 2 bots pick 3 items, 1 bot picks 2 → 3 deliveries, ~50 rounds

**Implementation**:
- Wire `_should_deliver_early()` into step chain (already exists, just needs gating)
- Add `_step_fill_up`: when bot has 1-2 active items and active items remain
  on shelves, continue picking instead of delivering
- Modify `_step_deliver_active` to check if filling up is cheaper

### A5: Eliminate Tail Bot Starvation (Nightmare +100-150)

**Current**: Bot 15-19 never get assignments because `_compute_bot_assignments()`
runs out of items before reaching them.
**Target**: ALL bots are always doing something productive.

The order has 4-6 items, but we have 20 bots. Only 4-6 bots get item assignments.
The rest fall through to preview/idle steps and mostly wait.

**Approach for unassigned bots** (the other 14-16 bots):
1. **Pre-position near predicted next items**: Analyze the preview order's items.
   Station unassigned bots at aisle entrances near those items. When the order
   activates, they're already adjacent.
2. **Courier role**: Unassigned bots without inventory stay near the dropoff
   corridor. When assigned bots pick up items, they "hand off" (not literally —
   but the courier can pick a nearby item while the picker continues).
3. **Speculative active pickup**: Even without assignment, bots near active items
   should pick them up. Currently only assigned bots or greedy-routed bots pick.

**Implementation**:
- Modify idle positioning to pre-stage bots near preview item locations
- Allow unassigned bots to use `_build_greedy_route` (currently skipped)
- Increase `active_picker_count` in `_assign_roles` for large teams

### A6: Collision-Aware Pathfinding (Expert +30-50, Nightmare +50-80)

**Current**: Bots plan paths ignoring other bots. Blocked moves waste rounds.
**Target**: Temporal BFS that avoids cells occupied by other bots in future rounds.

This is the hardest change but eliminates the "two bots stuck facing each other"
problem. With 20 bots on a 30x18 grid, collisions are frequent.

**Approach**:
1. Each round, build an occupancy map for the next 3-5 rounds based on
   predicted bot movements
2. Use A* with temporal dimension: (x, y, t) states
3. Wait-in-place if all moves are blocked (already done)

**Simpler alternative**: One-way aisle traffic. Left shelf column = move down,
right shelf column = move up. Aisle interiors = move in assigned direction.
This eliminates head-on collisions in aisles entirely.

**Implementation**:
- New: `pathfinding.py` temporal A* variant
- Modify `_emit_move_or_wait` to use temporal paths
- OR: simpler one-way aisle enforcement in movement.py

### A7: Order Completion Speed (All difficulties +10-20 each)

**Current**: 15.6 rounds/order on Nightmare. #1 does 6.25.
**Target**: Reduce to ~8 rounds/order through parallelism.

The +5 bonus per order is huge. Completing orders faster means more bonuses.
With 50 orders on Medium (300 rounds), going from 18 to 12 rds/order means
completing 25 vs 17 orders = +40 bonus points.

**Approach**:
1. **Parallel item assignment**: Assign ALL items of an order simultaneously
   to different bots. Currently some bots pick items already being picked by others.
2. **Completion-aware routing**: When 1 item remains, ALL idle bots should
   converge on it (closest bot wins, others pivot immediately).
3. **Pre-delivery staging**: Bots with active items stage near dropoff while
   the last item is being picked, so delivery is instant when picked.

### A8: Single-Bot Optimization (Easy +40-50)

Easy has 1 bot. Pure routing optimization. Currently 116, theoretical max ~425.
The bot completes 13 orders in 300 rounds = 23 rds/order.

**Target**: 17-18 orders = ~170 points.

**Approach**:
1. **Optimal route planning**: Use full game knowledge (all orders, all item
   positions) to plan the entire 300 rounds upfront
2. **Interleaved delivery**: Deliver items whenever passing near dropoff
3. **Route table optimization**: Current `get_optimal_route` is good but
   may not consider interleaved delivery opportunities
4. **Minimize empty travel**: After delivering, immediately route to the
   nearest item for the next order (currently does this but may not be optimal)

## Implementation Phases

### Phase 1: Quick Wins (expected +50-80 total)
- A4: Wire `_should_deliver_early()` + fill-before-deliver logic
- A2 (partial): Cap preview bots to 3 for large teams, eliminate waste
- Fix non-active clearing threshold for 4-7 bot teams
- A5 (partial): Allow unassigned bots to use greedy routing

### Phase 2: Zone System (expected +200-350 total)
- A1: Zone-based ownership for Expert/Nightmare
- A3: Delivery pipeline with ETA scheduling
- A5: Full tail bot activation

### Phase 3: Pathfinding + Routing (expected +100-200 total)
- A6: Collision-aware pathfinding (or one-way aisles)
- A7: Order completion speed improvements
- A8: Single-bot deep optimization

### Phase 4: Fine-Tuning (expected +50-100 total)
- Multi-cycle assignment
- Spawn-phase coordination
- Per-difficulty constant tuning
- Benchmark-driven iteration

## Key Metrics to Track

| Metric | Current (Nightmare) | Target | How |
|--------|-------------------|--------|-----|
| Rounds/order | 15.6 | 6-8 | A1, A3, A7 |
| Items/delivery | 1.40 | 2.5+ | A4 |
| Waste % | 81.2% | <20% | A2 |
| InvFull waits | 367 | <50 | A3, A4 |
| Tail bot idle rds | 450+ | <50 | A1, A5 |
| Bot utilization (min) | 7% | >70% | A1, A5 |
| Orders completed | 32 | 80+ | All |

## Risk Assessment

| Change | Risk | Mitigation |
|--------|------|------------|
| Zone ownership | High — could regress small teams | Gate to teams >= 8 only |
| Preview capping | Medium — cascade delivery depends on preview | Keep 2-3 preview bots |
| Fill-before-deliver | Medium — delays individual deliveries | Gate: skip when order completable |
| Collision-aware paths | High — performance cost, complexity | Start with one-way aisles (simpler) |
| Tail bot activation | Low — they're doing nothing now | Can only improve |

## Validation

Every change must:
1. TDD: write test first
2. Pass all 616+ existing tests
3. Run `python benchmark.py --diagnostics`
4. Check `docs/benchmark_results.md` — total must not regress
5. Run `python analyze_replay.py <log>` — verify metric improvements
6. Accept single-difficulty regression ≤10 if total improves ≥20
