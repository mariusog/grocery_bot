# Task Board

Agents MUST check this file before starting work and update it when claiming or completing tasks.

Status: `open` | `in-progress` | `done` | `blocked`

## Current Performance (2026-03-06)

| Difficulty | Bots | Sim Avg (20 seeds) | Live Score |
|------------|------|--------------------|------------|
| Easy       | 1    | 152.6              | 133        |
| Medium     | 3    | 114.3              | 110        |
| Hard       | 5    | 83.4               | 70         |
| Expert     | 10   | 57.5               | 46         |

Easy is near ceiling. Multi-bot efficiency is 10-25% of theoretical. Key finding from T15: delivery staggering is counterproductive — orders need ALL items delivered for the +5 bonus, so serializing delivery makes orders take longer.

---

## Open Tasks (priority order)

### T17: Full-Path Caching and Commitment
- **Agent**: pathfinding-agent
- **Status**: in-progress
- **Priority**: 1
- **Files**: `grocery_bot/pathfinding.py`, `grocery_bot/game_state.py`, `grocery_bot/planner/movement.py`
- **Description**: Currently bots recompute BFS every round, which can flip-flop between equally-good paths. Instead:
  1. When a bot starts heading to a target, compute the full path using `bfs_full_path`
  2. Cache it on GameState (`bot_planned_paths: dict[bot_id] -> list[pos]`)
  3. Follow the cached path step-by-step unless: (a) target changed, (b) next step is blocked by a new obstacle, (c) a shorter path opened up (check every 5 rounds)
  4. This eliminates path flip-flopping which is a major cause of oscillation
- **Success**: Oscillation count reduced by 30%+ vs current baseline.
- **Depends on**: none

### T21: Integrate Precomputed Route Tables into Pickup Logic
- **Agent**: strategy-agent
- **Status**: done
- **Priority**: 2
- **Files**: `grocery_bot/planner/pickup.py`
- **Description**: T16 added precomputed route tables to GameState (`best_pickup`, `best_pair_route`, `best_triple_route`, `get_optimal_route()`). These are not yet used by pickup logic. Integrate them:
  1. In `_build_single_bot_route`, use `gs.get_optimal_route()` instead of per-round TSP computation
  2. In `_build_greedy_route`, use `gs.best_pickup[type]` for faster candidate scoring
  3. This eliminates route flip-flopping since routes are deterministic from round 0
- **Success**: Easy avg maintained. Route computation time reduced.
- **Depends on**: T16 (done)
- **Result**: Integrated precomputed routes into both single-bot and greedy pickup. All 327 tests pass, no score regression.

### T22: Improve Multi-Bot Coordination for Expert
- **Agent**: strategy-agent
- **Status**: open
- **Priority**: 3
- **Files**: `grocery_bot/planner/round_planner.py`, `grocery_bot/planner/assignment.py`
- **Description**: Expert scores 57.5 avg (10 bots) vs theoretical ~467. The coordination infrastructure from T15 exists but gains were minimal. Key areas to explore:
  1. **Smarter role transitions**: Bots should switch from active-picker to preview-picker sooner when order is nearly complete (1-2 items remaining)
  2. **Reduce duplicate item targeting**: Even with Hungarian assignment, bots sometimes race to the same item type from different shelves. Use `gs.best_pickup` to always pick the optimal shelf.
  3. **Cooperative order completion**: When order has 1 item left, ALL other bots should immediately switch to preview/idle instead of competing for that last item.
- **Success**: Expert avg > 75. No regression on Easy/Medium.
- **Depends on**: T15 (done), T16 (done)

### T18: Benchmark Phase 2 Changes
- **Agent**: qa-agent
- **Status**: open
- **Priority**: 4 — run after T17, T21, T22
- **Files**: `benchmark.py`, `docs/benchmark_results.md`
- **Description**: Full benchmark and regression test update.
  1. Run 20-seed benchmark across all difficulties
  2. Update score regression thresholds to new baselines
  3. Profile per-round timing (must stay under 2s/round for live server)
  4. Run on live server to validate simulator results
- **Success**: All tests pass. Live server scores within 15% of simulator.
- **Depends on**: T17, T21, T22

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

### Code Quality
| Task | Result |
|------|--------|
| T19: Single-responsibility refactor | Globals eliminated, 33 unit tests added, type hints on all code. |
| T20: Package structure | `grocery_bot/` package with `planner/` subpackage. Matching test dirs. |
| T23: Unit test coverage audit | Added 97 tests across all modules (230 -> 327). Every public method now has 2+ tests. |

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
