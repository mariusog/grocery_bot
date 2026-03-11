# Improvement Plan (2026-03-11 v2)

## Key Insight

We already score the **theoretical maximum** for every order we complete:
score = (completed_orders × 5) + items_delivered. The ONLY way to gain
points is to **complete more orders**, which means completing each order
faster so more fit in 300/500 rounds.

## Current Simulator Scores (recorded maps)

| Diff | Bots | Score | Done | Recorded | Missed | Avg rds/order | O1 time | Potential |
|------|------|-------|------|----------|--------|---------------|---------|-----------|
| Easy | 1 | 133 | 16 | 18 | 2 | 16.5 | 25 | +16 |
| Medium | 3 | 148 | 16 | 20 | 4 | 17.4 | 25 | +36 |
| Hard | 5 | 135 | 14 | 14 | 0 | 20.3 | 40 | 0 |
| Expert | 10 | 124 | 12 | 13 | 1 | 22.8 | 70 | +9 |
| Nightmare | 20 | 327 | 30 | 32 | 2 | 16.1 | 52 | +18 |
| **Total** | | **867** | **88** | **97** | **9** | | | **+79** |

Hard is already perfect (14/14). The gains are in Medium (+36), Nightmare
(+18), Easy (+16), and Expert (+9).

## Root Cause: Opening Round Waste

The single biggest bottleneck across ALL maps is the first order. Evidence:

- **Expert O1 takes 70 rounds** (23% of the entire 300-round game)
- **Nightmare O1 takes 52 rounds** (10% of 500 rounds, with 20 bots!)
- **Hard O1 takes 40 rounds** (13% of 300 rounds)
- Every subsequent order averages 15-20 rounds

Why O1 is so slow:
1. All bots spawn at ONE cell (bottom-right corner)
2. Only 1-2 bots can move per round (rest blocked by each other)
3. Spawn is 19-27 cells from the dropoff (opposite corners)
4. No spawn dispersal for teams < 10 bots

**On Expert R0: 8 of 10 bots WAIT doing nothing.** On Nightmare R0: 18 of
20 bots WAIT. This is pure waste.

## Improvement Tasks

### T1: Enable spawn dispersal for 3+ bot teams
**Target**: Medium, Hard, Expert | **Mechanism**: change threshold

Currently `use_spawn_dispersal` requires `num_bots >= 10`. Medium (3 bots)
and Hard (5 bots) have no dispersal — bots stack at spawn and trickle out
one per round. On Hard, this means R0-R3 has 3 of 5 bots doing nothing.

**Change**: Lower `use_spawn_dispersal` threshold from 10 to 3.

**Files**: `grocery_bot/team_config.py` (line 199)

**Benchmark**: Compare O1 completion time before/after. Target: -5 rounds
on Hard O1 (40→35), -3 rounds on Medium O1 (25→22).

**Go/revert**: Keep if total score >= 867 AND no map drops > 5 points.

### T2: Reduce first-order time by skipping preview work until O1 completes
**Target**: All maps | **Mechanism**: step chain guard

During O1, bots waste rounds picking up preview items and doing speculative
work instead of focusing 100% on active items. Evidence:

- Medium R2: B0 picks up pasta (active) but B2 walks LEFT away from items
- Hard R0-R5: B1/B2/B4 wait at spawn while B0/B3 disperse, then some bots
  pick preview items before finishing O1
- Expert: 10 bots, only ~3 work on O1's 5 items, rest speculate

**Change**: In `_step_opportunistic_preview`, `_step_preview_prepick`, and
`_step_speculative_pickup`: skip if `current_round <= first_order_deadline`
where `first_order_deadline = items_in_first_order * 8` (heuristic: ~8
rounds per item for first order).

**Files**: `grocery_bot/planner/steps.py` (3 step methods)

**Benchmark**: Compare O1 time and total orders across all maps.

**Go/revert**: Keep if total score >= 867. Revert if Medium or Nightmare
drop > 5 points (they rely on preview prepicking).

### T3: Faster spawn exit — pick any adjacent item immediately
**Target**: All multi-bot maps | **Mechanism**: pickup step

When bots are stacked at spawn, they wait for space to move. But if there's
an item adjacent to the spawn cell, ANY bot could pick it up instead of
waiting. Currently `_step_active_pickup` requires net_active > 0 for the
item type, which is true — but the bot might not have an assignment and
the greedy route fails because it's blocked.

**Change**: In the first N rounds (while bots are still stacked at spawn),
allow any bot to pick up any adjacent item regardless of assignment. This
turns idle wait rounds into productive pickup rounds.

**Files**: `grocery_bot/planner/steps.py` (new early-round guard in
`_step_active_pickup`)

**Benchmark**: Check if bots pick items earlier in R0-R5.

**Go/revert**: Keep if total >= 867 and O1 time improves by >= 2 rounds.

### T4: Fix Nightmare idle bots (B18/B19 do almost nothing)
**Target**: Nightmare | **Mechanism**: role rebalancing

On the Nightmare map, bot distribution is wildly unbalanced:
- B0: 17 pickups, B6: 5 pickups, B16: 3, B18: 3, B19: 1 pickup
- B19 idles 91 consecutive rounds (R270-R360), then 80 more (R178-R257)
- B18 has 22% utilization (78% idle)

These bots are assigned to dead zones with no items. They walk to corners
and starve. With 20 bots, having 2-3 completely idle costs ~20 points.

**Change**: Add an idle-timeout mechanism — if a bot has been idle for
>= 15 rounds, reassign it to a zone with active items. Implementation:
track `rounds_since_last_pickup` per bot, force re-routing when threshold
exceeded.

**Files**: `grocery_bot/planner/idle.py` (new method),
`grocery_bot/planner/steps.py` (new step or guard)

**Benchmark**: Check B18/B19 utilization rises from 22-26% to >= 50%.

**Go/revert**: Keep if Nightmare >= 327 and idle bot pickups increase.

### T5: Deliver non-active items at dropoff for free points
**Target**: Expert, Nightmare | **Mechanism**: step guard

Bots that arrive at the dropoff with non-active items currently walk away
without delivering. Each item is worth +1 point. Delivering costs 1 round
(the drop_off action) which is cheap when already at the cell.

BUT: naive "deliver any items at dropoff" caused -100 regression in testing
because bots CHOSE to go to dropoff to deliver junk instead of picking
active items.

**Change**: Only deliver non-active items IF the bot is already AT the
dropoff (distance == 0) AND has no active assignment. This is truly free —
the bot was there anyway and has nothing better to do.

**Files**: `grocery_bot/planner/steps.py` (`_step_deliver_at_dropoff`)

**Benchmark**: Check for score gain without regression.

**Go/revert**: Keep if total >= 867 and no map drops > 2 points.

## Implementation Order

1. **T5** first — smallest change, safest, potentially free points
2. **T1** next — simple config change, enables faster starts
3. **T2** then — focused first-order improvement
4. **T3** after — complements T1/T2 for opening efficiency
5. **T4** last — most complex, Nightmare-only

## Verification Protocol

After each change:
1. `python -m pytest tests/ -q --tb=line -m "not slow" 2>&1 | tail -20`
2. `python benchmark.py --diagnostics` (replay maps)
3. Compare total score (must be >= 867)
4. Compare O1 completion round per map
5. If score drops on ANY map by > 5, revert immediately

## What NOT To Do (learned from v1 failures)

- Do NOT raise `max_nonactive_deliverers` for 8+ bots (causes dropoff gridlock)
- Do NOT skip `_step_active_pickup` for unassigned bots (starves item pickup)
- Do NOT deliver non-active items by routing bots TO the dropoff (wastes rounds)
- Do NOT move `_step_break_oscillation` earlier in the chain (large-team regression)
- Do NOT lower `nonactive_clear_min_inv` for medium teams (tested: -95 regression)
