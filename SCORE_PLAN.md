# Score Improvement Plan: Target 700+

## Current Scores (Live Server)

| Difficulty | Bots | Score | Orders | Items |
|-----------|------|-------|--------|-------|
| Easy | 1 | 126 | - | - |
| Medium | 3 | 126 | - | - |
| Hard | 5 | 138 | - | - |
| Expert | 10 | 64 | - | - |
| Nightmare | 20 | 78 | - | - |
| **Total** | | **532** | | |

**Target: 700+ (need +168)**

## Local Benchmark Baselines

| Difficulty | seed=42 (bot.decide_actions) | seed=42 (fresh GS) | recorded map |
|-----------|------------------------------|---------------------|-------------|
| Easy | 143 | 143 | 94 (126 live) |
| Medium | 141 | 141 | 124 |
| Hard | 110 | 110 | 111 |
| Expert | **4** | **64** | **52** |
| Nightmare | 108 | 108 | 78 |

---

## Critical Bug: Route Table Precomputation Breaks Expert (P0)

**Root cause**: `init_static()` precomputes route tables (`best_pickup`, `best_pair_route`, `best_triple_route`) when `drop_off` is in the state dict. `bot.decide_actions()` passes the full state (with `drop_off`), while fresh `GameState` + `RoundPlanner` passes `{grid, items}` only (no `drop_off`).

**Effect**: With route tables, `_build_greedy_route` uses `best_pickup[type]` which returns a single globally-optimal cell per type. Multiple bots converge on the same cells, pick up non-active items that happen to be nearby, fill their inventory with useless items, and get permanently stuck (score 4 vs 64).

**Fix**: Disable route table precomputation for multi-bot games (>= 3 bots), or only use route tables in `_build_single_bot_route` (single-bot path). The route tables were designed for the 1-bot Easy mode optimization and actively harm multi-bot coordination.

**Expected gain**: Expert 4 → 60-85 (+56-81 points on benchmark)

**Files**: `grocery_bot/game_state/state.py` (init_static), `grocery_bot/planner/pickup.py` (_build_greedy_route)

---

## High-Impact Improvements

### 1. Non-Active Inventory Clearing for Large Teams (P1)

**Problem**: `_step_clear_nonactive_inventory` returns `False` for teams >= `PREDICTION_TEAM_MIN` (8 bots). Bots with full inventory of non-active items can never clear them, wasting bot capacity for 200+ rounds.

**Fix**: Allow large teams to clear non-active inventory, with a concurrency limit (e.g., max 2-3 at a time) to avoid dropoff congestion.

**Expected gain**: Expert +10-15, Nightmare +10-15

**Files**: `grocery_bot/planner/steps.py` (_step_clear_nonactive_inventory)

### 2. Spawn Bottleneck Dispersal (P1)

**Problem**: All bots start at the same spawn point. With 10-20 bots, only 2 can move per round (up and left). Bots 5-9 wait 5-10 rounds before moving at all. Bot 9 waits 71% of all rounds.

**Fix**: Add a spawn dispersal phase in the first N rounds. Instead of all bots trying to BFS to their targets (which creates a jam), assign explicit dispersal directions: half go up, half go left, staggered by bot ID. This gets all bots moving within 2-3 rounds instead of 8-10.

**Expected gain**: Expert +5-10, Nightmare +5-10

**Files**: `grocery_bot/planner/movement.py` or new step in `steps.py`

### 3. Smarter Delivery Queue for Large Teams (P2)

**Problem**: `MAX_CONCURRENT_DELIVERERS` limits to `max(2, num_bots // 4)` = 2-5. With 20 bots and many carrying active items, only a few can deliver at a time. Others queue and wait.

**Fix**: Dynamically adjust deliverer limit based on:
- Distance to dropoff (let close bots deliver immediately)
- Number of bots with active items waiting
- Whether dropoff is actually congested

**Expected gain**: Nightmare +10-15

**Files**: `grocery_bot/planner/coordination.py`

### 4. Preview Item Strategy for Multi-Bot (P2)

**Problem**: Idle bots (those not assigned active items) don't efficiently pre-pick preview items. With 10+ bots and only 4-6 active items per order, half the bots are idle.

**Fix**: Aggressive preview picking for idle bots — send them to pick up items that are likely needed in the next order. More preview bots = faster next-order completion. Currently limited to 2 extra preview bots for 8+ teams.

**Expected gain**: Expert +5-10, Nightmare +5-10

**Files**: `grocery_bot/planner/coordination.py` (_assign_roles), `grocery_bot/planner/steps.py`

### 5. Endgame Optimization (P2)

**Problem**: `ENDGAME_ROUNDS_LEFT = 40` may be too conservative. Bots start rushing to deliver when 40 rounds remain, but could still pick up more items.

**Fix**: Dynamic endgame threshold based on bot count and map size. With 10+ bots, more items can be collected in parallel, so trigger endgame later (20-25 rounds).

**Expected gain**: All difficulties +2-5 each

**Files**: `grocery_bot/constants.py`, `grocery_bot/planner/steps.py`

---

## Medium-Impact Improvements

### 6. Avoid Picking Non-Active Items Early (P2)

**Problem**: Bots with spare slots pick up preview items opportunistically, but these fill inventory and delay active item delivery. On multi-bot teams, this is especially harmful — bots end up with 3 non-active items and can't pick active items.

**Fix**: For large teams, only allow preview picking if: (a) bot has no active assignment, (b) bot is already near a preview item, (c) bot has no clear path to active items.

**Expected gain**: Expert +5, Nightmare +5

### 7. Better Idle Positioning (P3)

**Problem**: Idle bots use heuristic positioning that sometimes leaves them far from where they'll be needed. Bot 9 in Expert is idle 71% of the time.

**Fix**: Position idle bots near the items most likely needed by the next order (preview order). Reduce idle wait% from 71% to ~20%.

**Expected gain**: Expert +3-5

---

## Implementation Priority

| # | Task | Expected Gain | Effort | Priority |
|---|------|---------------|--------|----------|
| P0 | Fix route table bug | +60-80 (Expert) | Small | **IMMEDIATE** |
| P1a | Non-active clearing for large teams | +20-30 | Small | High |
| P1b | Spawn dispersal | +10-20 | Medium | High |
| P2a | Dynamic delivery queue | +10-15 | Medium | Medium |
| P2b | Preview strategy for multi-bot | +10-20 | Medium | Medium |
| P2c | Dynamic endgame threshold | +10-25 | Small | Medium |
| P2d | Restrict early preview picking | +10 | Small | Medium |
| P3 | Better idle positioning | +3-5 | Medium | Low |

**Conservative total gain: +133-205 → Target 665-737**
**With P0 bug fix alone: +60-80 → ~592-612**

---

## Execution Order

1. **P0**: Fix route table bug (immediate, biggest single gain)
2. **P1a**: Enable non-active clearing for large teams
3. **P1b**: Spawn dispersal phase
4. **P2c**: Dynamic endgame threshold (easy win)
5. **P2a**: Dynamic delivery queue
6. **P2b**: Aggressive preview strategy
7. **P2d**: Restrict early preview picking
8. **P3**: Better idle positioning

After each change: run `benchmark.py --quick` and `benchmark.py --map-dir maps/` to validate.
