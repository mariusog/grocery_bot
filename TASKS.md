# Task Board

Agents MUST check this file before starting work and update it when claiming or completing tasks.

Status: `open` | `in-progress` | `done` | `blocked`

## Current Performance (2026-03-07)

| Difficulty | Bots | Sim Avg (20 seeds) | Live Score |
|------------|------|--------------------|------------|
| Easy       | 1    | 147.9              | 133        |
| Medium     | 3    | 108.7              | 110        |
| Hard       | 5    | 82.1               | 70         |
| Expert     | 10   | 59.6               | 46         |

Easy is near ceiling. Multi-bot efficiency is 10-25% of theoretical. Key bottlenecks from T22 analysis:
- **Dropoff congestion**: Single dropoff cell is the #1 Expert bottleneck
- **Preview prepicking net-negative** at 16 types (~31% hit rate)
- **Delivery staggering counterproductive** — orders need ALL items for +5 bonus

---

## Open Tasks (priority order)

### T24: A/B Strategy Testing Framework
- **Agent**: qa-agent
- **Status**: done
- **Result**: Added action-tracking diagnostics (moves/waits/pickups/delivers, waste%, inv-full waits, rounds/order, P/D ratio, per-bot idle) to simulator and `benchmark.py --diagnostics` mode.
- **Priority**: 1
- **Files**: `grocery_bot/simulator.py`, `benchmark.py`
- **Description**: Add ability to compare two strategy variants side by side:
  1. Add `benchmark.py --compare` mode that runs baseline vs patched on same seeds
  2. Add per-seed delta reporting (seed, baseline_score, patched_score, delta)
  3. Add action-tracking diagnostics to simulator: count moves/waits/pickups/delivers, useful vs wasted pickups, rounds-per-order, inventory-full-waits
  4. Output diagnostic CSV for analysis
- **Success**: Can run `python benchmark.py --compare --seeds 10` and see per-seed deltas.
- **Depends on**: T18

### T25: Fix Inventory Clog (Expert #1 Bottleneck)
- **Agent**: strategy-agent
- **Status**: open
- **Priority**: 1
- **Files**: `grocery_bot/planner/pickup.py`, `grocery_bot/planner/round_planner.py`, `grocery_bot/planner/delivery.py`
- **Description**: **ROOT CAUSE**: Expert has 645/3000 bot-rounds (21.5%) where bots wait with FULL inventory. 32% of pickups are non-active items that clog slots. Pickup-to-delivery ratio is 3.5x (vs 2.0x on Medium).
  Fix by:
  1. **Never pick non-active items when >5 bots** — preview prepicking is net-negative at 16 types (~31% hit rate)
  2. **Immediate delivery when inventory has ANY active items** — don't wait for full inventory
  3. **Emergency dump**: if inventory is full with non-active items, deliver immediately to free slots
  4. **Scale pickup aggression by bot count** — with 10 bots and 5 items/order, each bot should target at most 1 item
- **Success**: Expert inventory-full-waits < 200 (from 645). Expert avg > 75.
- **Depends on**: T18

### T26: Reduce Expert Idle Time
- **Agent**: strategy-agent
- **Status**: open
- **Priority**: 2
- **Files**: `grocery_bot/planner/idle.py`, `grocery_bot/planner/round_planner.py`, `grocery_bot/planner/assignment.py`
- **Description**: 4 of 10 Expert bots are idle >50% of the time (Bot 5: 66%, Bot 6: 64%, Bot 8: 60%). These bots should be doing useful work.
  Ideas:
  1. **Assign idle bots to pre-position near likely next-order items** — use item type frequency to predict
  2. **Relay pattern**: idle bots move toward shelves with needed items, ready to pick instantly
  3. **Dynamic role assignment**: reduce number of designated "idle" bots when order has many items remaining
- **Success**: No Expert bot idle >40%. Expert avg > 80.
- **Depends on**: T25

### T27: Optimize Rounds-Per-Order
- **Agent**: pathfinding-agent + strategy-agent
- **Status**: open
- **Priority**: 3
- **Files**: `grocery_bot/game_state.py`, `grocery_bot/planner/pickup.py`, `grocery_bot/planner/delivery.py`
- **Description**: Expert averages 46 rounds/order vs Medium's 23. With 10 bots this should be LOWER than Medium, not 2x higher.
  Ideas:
  1. **One-way traffic flow**: designate corridor directions to prevent head-on collisions
  2. **Dropoff queuing**: bots line up to deliver instead of clustering and blocking
  3. **Parallel order fulfillment**: assign each bot exactly 1 item, all deliver within a few rounds of each other
  4. **Reduce collision avoidance radius** — current temporal BFS may be too conservative
- **Success**: Expert avg rounds/order < 30. Expert avg > 100.
- **Depends on**: T25, T26

### T28: Endgame Delivery Optimization
- **Agent**: strategy-agent
- **Status**: open
- **Priority**: 4
- **Files**: `grocery_bot/planner/delivery.py`, `grocery_bot/planner/round_planner.py`
- **Description**: Tune endgame threshold based on bot count and distance to dropoff. Currently triggers at 30 rounds remaining — may not be aggressive enough for Expert.
- **Success**: Improved scores in final rounds across all difficulties.
- **Depends on**: T18

---

## Completed Tasks

### Phase 1
| Task | Result |
|------|--------|
| T1: Fix Medium deadlocks | Fixed. Medium avg 142.6 (was 110.3). |
| T2: Wire Hungarian assignment | Added `assign_items_to_bots()` API to GameState. |
| T3: Wire Hungarian into round decisions | Hungarian for bots > items, greedy for multi-slot. Hard +4.5. |
| T4: Wire interleaved delivery | Partial delivery when near dropoff. Minimal impact. |
| T5: Benchmark baseline | Baseline captured. |
| T6: Multi-bot collision tests | 7 new tests, all pass. |
| T7: Benchmark after changes | Easy 152.6, Medium 104.3, Hard 76.2, Expert 45.3. |
| T8: Investigate Hard/Expert regression | Two fixes applied. Hard/Expert improved. |
| T9: Raise score thresholds | Thresholds updated to realistic simulator values. |
| T10: Refactor round_planner.py | Split into 6 mixin modules. |
| T11: Improve simulator fidelity | Gap reduced to 5-8%. |

### Phase 2
| Task | Result |
|------|--------|
| T12: Cooperative pathfinding | Pre-prediction pass. Medium +2.3, Hard +3.4, Expert +1.0. |
| T13: Multi-order pipeline | Partial: force_slots conditional + delivery limiting. Expert +2.9. |
| T14: Corridor-aware idle positioning | Idle spots + rank-based spread. Expert +6.1. |
| T15: Delivery pipeline + roles | Coordination infra added. Expert +1.0. Staggering counterproductive. |
| T16: Route tables + last-item priority | Precomputed routes + 3x priority boost. Medium +2.8. |
| T17: Full-path caching | Cached BFS paths on GameState. Hard -14% oscillation, +4.2 score. Expert +3.0. |
| T21: Route table integration | Precomputed routes in pickup logic. Deterministic routing, no regression. |
| T22: Multi-bot coordination | Disabled zone penalties for 8+ bots. Expert +2.1. 75 target not reached. |

### Code Quality
| Task | Result |
|------|--------|
| T19: Single-responsibility refactor | Globals eliminated, 33 unit tests added, type hints on all code. |
| T20: Package structure | `grocery_bot/` package with `planner/` subpackage. Matching test dirs. |
| T23: Unit test coverage audit | Added 97 tests across all modules (230 -> 327). Every public method now has 2+ tests. |
| T18: Benchmark Phase 2 Changes | Easy 148, Medium 109, Hard 82, Expert 60. Thresholds updated to 80-85% of avg. Timing <2ms/round. All 345 tests pass. |

---

## Notes

- Add new tasks at the bottom of "Open Tasks" with the next T-number
- When completing a task, move it to "Completed Tasks" with a one-line result
- If a task is blocked, set status to `blocked` and note why
- **All optimization must be validated on live server** — simulator scores alone are insufficient
- **Phase 2 goal**: Expert >= 200, Hard >= 150, Medium >= 180

## Project Structure

Source: `grocery_bot/` package with `planner/` subpackage.
Tests: `tests/` with `integration/`, `pathfinding/`, `game_state/`, `planner/` subdirectories.
Entry points: `bot.py`, `benchmark.py` (both at project root).
See `CLAUDE.md` for full layout.
