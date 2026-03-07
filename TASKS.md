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

### T24: Dropoff Congestion Mitigation
- **Agent**: pathfinding-agent + strategy-agent
- **Status**: open
- **Priority**: 2
- **Files**: `grocery_bot/game_state.py`, `grocery_bot/planner/movement.py`, `grocery_bot/planner/delivery.py`
- **Description**: Single dropoff cell is the #1 Expert bottleneck (T22 finding). When multiple bots try to deliver simultaneously, they block each other. Ideas:
  1. Pathfinding-agent: Add dropoff-aware collision avoidance — bots approaching dropoff should queue in a line rather than clustering
  2. Strategy-agent: Stagger delivery timing — if another bot is within 2 steps of dropoff, wait or pick up nearby items instead
  3. Reduce blocking radius near dropoff for delivering bots
- **Success**: Expert avg > 70. No regression on Easy/Hard.
- **Depends on**: T18

### T25: Disable Preview Prepicking on Expert
- **Agent**: strategy-agent
- **Status**: open
- **Priority**: 3
- **Files**: `grocery_bot/planner/pickup.py`, `grocery_bot/planner/round_planner.py`
- **Description**: T22 found preview prepicking is net-negative at 16 item types (~31% hit rate). Filling inventory with previews prevents active pickups. Disable or heavily restrict preview picking when `num_item_types > 12` or `num_bots > 5`.
- **Success**: Expert avg improvement. No Easy/Medium regression.
- **Depends on**: T18

### T26: Endgame Delivery Optimization
- **Agent**: strategy-agent
- **Status**: open
- **Priority**: 4
- **Files**: `grocery_bot/planner/delivery.py`, `grocery_bot/planner/round_planner.py`
- **Description**: In the last 30-50 rounds, bots should focus exclusively on delivering what they have rather than starting new pickups. Currently `_step_endgame` triggers at 30 rounds but may not be aggressive enough. Tune endgame threshold based on bot count and inventory state.
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
