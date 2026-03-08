# Active Item Priority Plan

## Problem Statement

Completing active orders gives **+5 bonus points** and reveals the next preview order sooner.
Our bot had a fundamental issue: `_step_opportunistic_preview` (step 6) fires before
`_step_active_pickup` (step 10), so a bot adjacent to both an active and preview item
picks the preview item instead of the higher-value active item.

## Confirmed Mechanics

- **Drop-off is atomic**: one `drop_off` action delivers ALL matching items from inventory
- **Items don't need sequential delivery** within an order — all matching items deliver at once
- **Cascade**: if delivery completes an order, remaining inventory is re-checked against the
  new active order in the same action
- **Non-matching items stay** in inventory after drop-off

## Fix 1: Three-layer guard on `_step_opportunistic_preview` [DONE]

**Status**: Implemented, zero regression (1738 → 1738)

**File**: `grocery_bot/planner/steps.py` (lines 113–147)

Three guards skip preview pickup when active items should be prioritized:

1. **Solo bots**: `active_on_shelves > 0` — solo bots must always focus active
2. **Small teams (<3 bots)**: `bot_assignments.get(ctx.bid)` — assigned bots on small
   teams skip preview to complete active orders faster
3. **Any team**: adjacent active item scan — if an active item is adjacent, skip preview
   and let `_step_active_pickup` (step 10) handle it

**Why these specific thresholds**:
- Broad guard (all bots, all teams): regressed −190. Too aggressive — blocks useful
  cascade pre-picking on larger teams.
- Assignment guard for ≤3 bots: regressed −20 on one Medium map. 3-bot teams need
  cascade flexibility.
- Assignment guard for <3 bots: zero regression. 1-2 bot teams are small enough that
  every turn matters for order completion speed.
- Adjacent-active guard: zero regression by definition — it only changes behavior when
  the bot would pick preview instead of an equally-accessible active item.

**Tests**: `tests/planner/test_active_priority.py` (5 tests):
- `test_adjacent_active_preferred_over_adjacent_preview`
- `test_no_preview_pickup_when_active_on_shelves`
- `test_multi_bot_active_priority`
- `test_active_priority_with_two_dropoff_zones`
- `test_bot_uses_nearest_dropoff_for_delivery`

---

## Fix 2: Cap `_spare_slots` for unassigned bots [REJECTED]

**Status**: Tested, reverted. Caused −87 additional regression.

Setting `reserve=1` for unassigned bots blocked useful preview pre-picking in
`_step_preview_prepick`. After Fix 1, the assignment guard already prevents assigned
bots from diverting to preview. Unassigned bots SHOULD use full capacity for preview —
they're surplus bots with no active work.

---

## Fix 3: Round-trip cost in bot assignment [DEFERRED]

Adding `dist(pickup_cell, dropoff)` to assignment cost regressed Medium by −50.
The pickup cell varies by bot, creating non-uniform bias in the Hungarian algorithm.

**Better approach** (for later): Use the item's shelf position (constant across bots)
for dropoff distance, scaled down to avoid dominance:
```python
item_to_drop = self.dist_static(tuple(it["position"]), drop_off)
d += item_to_drop * 0.3
```

---

## Fix 4: Bot convergence prevention [EXISTING]

Already handled by zone penalties, aisle staggering, and `_claim()` deduplication.
No additional changes needed.

---

## Results

| Approach | Total | vs Baseline |
|----------|-------|-------------|
| Baseline (no changes) | 1738 | — |
| Broad guard (all bots) | 1548 | −190 |
| Assignment guard (≤3 bots) | 1719 | −19 |
| Assignment guard (<3 bots) + adjacent guard | **1738** | **0** |
| + spare_slots reserve=1 | 1595 | −143 |

## Validation Protocol

**Progressive validation — simple maps first.** Verify correctness on Easy/Medium before
testing harder difficulties. Regressions on complex maps may be transient side-effects
of fixing fundamental behavior — accept them short-term if Easy/Medium improve.

After each fix:
1. `python -m pytest tests/ -q --tb=line -m "not slow" 2>&1 | tail -20` — all tests pass
2. `python benchmark.py --synthetic -d Easy --quick` — verify Easy score improves or holds
3. `python benchmark.py --synthetic -d Medium --quick` — verify Medium score improves or holds
4. If Easy+Medium look good, run full `python benchmark.py` for the complete picture
5. **Accept short-term regression** on Expert/Nightmare if the behavior is fundamentally
   more correct — those maps have compounding issues (congestion, convergence) that will
   be addressed in later fixes. The goal is correct foundations first, then tune.

## Key Principles

1. **Targeted guards, not broad blocks.** Only block preview when there's a specific
   reason (adjacent active item, small team with assignment). Broad blocks destroy
   cascade pre-picking which is a major scoring mechanism.

2. **Correct behavior first, optimize later.** Some regressions are expected when fixing
   fundamental priority issues. The +5 order completion bonus compounds over the full
   game and will win out.
