# Task Board

Agents MUST check this file before starting work and update it when claiming or completing tasks.

Status: `open` | `in-progress` | `done` | `blocked`

## Current Performance (2026-03-06)

| Difficulty | Bots | Sim Avg (20 seeds) | Live Score | Theoretical ~70% util |
|------------|------|--------------------|------------|----------------------|
| Easy       | 1    | 152.6              | 133        | ~102                 |
| Medium     | 3    | 114.3              | 110        | ~236                 |
| Hard       | 5    | 83.4               | 70         | ~286                 |
| Expert     | 10   | 57.5               | 46         | ~467                 |

Note: Hard orders corrected to (3, 5) matching challenge spec (was incorrectly (4, 6)).

Easy is near ceiling. **Multi-bot efficiency is 10-25% of theoretical.** The gap is NOT from pathfinding bugs — bots move but coordinate terribly. 20% of Expert bot-rounds are wasted on oscillation. Max delivery gap is 47 rounds.

---

## Open Tasks — Phase 2 (priority order)

### T12: Cooperative Pathfinding with Pre-Prediction
- **Agent**: pathfinding-agent
- **Status**: done
- **Result**: Implemented pre-prediction pass in `_pre_predict()` — estimates where each bot will move before detailed planning begins. Delivering bots predicted toward dropoff, assigned bots toward their first item, others stay put. Temporal BFS now has better info about undecided bots. Reservation table approach was tested but abandoned (too expensive, unreliable paths). Medium +2.3, Hard +3.4, Expert +1.0. Oscillation Expert 690→622.
- **Priority**: 1
- **Files**: `movement.py`, `round_planner.py`, `game_state.py`
- **Depends on**: none

### T13: Multi-Order Pipeline with Parallel Picking
- **Agent**: strategy-agent
- **Status**: done (partial)
- **Result**: Full pipeline model (ceil(items/3) active bots) regressed Hard/Medium due to dropoff congestion. Partial gains kept: (1) Step 6 force_slots conditional — 6+ bots only fill all preview slots when active_on_shelves==0, preventing inventory clog; (2) Step 7b non-active delivery limited to 1 concurrent deliverer for 5+ bots, reducing dropoff congestion. Expert 47.5→50.4 (+2.9), all others neutral. Root cause analysis: 1033 bot-rounds/game with full non-active inventory clogging, Step 7/7b oscillation between clear-dropoff and deliver-for-points.
- **Priority**: 2
- **Files**: `round_planner.py`
- **Depends on**: T12

### T14: Corridor-Aware Idle Positioning
- **Agent**: strategy-agent
- **Status**: done
- **Result**: For 8+ bots (Expert), idle bots now target precomputed walkable idle spots (unique per bot via rank-based spread) instead of unreachable shelf cells, and use predicted positions for active bots in crowd avoidance. Stay-still bias at idle spots reduces oscillation. Smaller teams keep original shelf targeting. Expert 50.4→56.5 (+6.1), all others unchanged. All 137 tests pass.
- **Priority**: 3
- **Files**: `idle.py`, `game_state.py`
- **Description**: Infrastructure already added in game_state.py (`idle_spots`, `corridor_y`). Currently idle bots target item shelf positions (blocked cells they can never reach) using `bid % len(xs)`, causing oscillation near shelves. Change to:
  1. Use precomputed `gs.idle_spots` (walkable aisle-entrance positions on corridor rows)
  2. Assign each bot a unique zone of idle spots (divide spots by bot count)
  3. Keep greedy 1-step movement style (don't use full BFS for idle — it interferes)
  4. Use predicted positions of other bots (not just current) for crowd avoidance
- **Success**: Expert idle% < 5% (currently 15%). No oscillation increase.
- **Depends on**: none (game_state.py infra already committed)

### T15: Delivery Pipeline + Persistent Assignments + Role Specialization
- **Agent**: strategy-agent
- **Status**: done (partial)
- **Result**: Implemented coordination infrastructure: (1) Order transition detection clears stale persistent state on order change. (2) Delivery queue on GameState tracks which bots should deliver, ordered by proximity/inventory. (3) Role assignment (pick/deliver/preview/idle) based on game state. (4) Persistent task assignments with commitment periods. (5) Enhanced preview bot selection for Expert (10+ bots). Key finding: delivery staggering (only 1 bot to dropoff) is fundamentally counterproductive — orders need ALL items delivered, so serializing delivery makes orders take 5x longer. Expert 56.5→57.5 (+1.0), no regressions. Infrastructure ready for future decision-influencing changes.
- **Priority**: 1
- **Files**: `round_planner.py`, `game_state.py`, `constants.py`
- **Depends on**: T19 (done)

### T16: Precomputed Route Tables + Last-Item Priority
- **Agent**: pathfinding-agent
- **Status**: done
- **Result**: Implemented in `game_state.py` and `constants.py`. (1) Precomputed route tables: `best_pickup` (per type), `best_pair_route` (all 2-type combos), `best_triple_route` (all 3-type combos) populated in `init_static()`. `get_optimal_route()` API for strategy-agent to use. (2) Last-item priority boost: when ≤2 candidate items in `assign_items_to_bots()`, cost multiplied by 0.33 so closest bot is strongly assigned. Medium +2.8, no regression on any difficulty. Route table usage in pickup.py pending strategy-agent integration.
- **Priority**: 2
- **Files**: `game_state.py`, `constants.py`
- **Depends on**: T19 (done)

### T17: Full-Path Caching and Commitment
- **Agent**: pathfinding-agent
- **Status**: open
- **Priority**: 3
- **Files**: `pathfinding.py`, `game_state.py`, `movement.py`
- **Description**: Currently bots recompute BFS every round, which can flip-flop between equally-good paths. Instead:
  1. When a bot starts heading to a target, compute the full path using `bfs_full_path`
  2. Cache it on GameState (`bot_planned_paths: dict[bot_id] -> list[pos]`)
  3. Follow the cached path step-by-step unless: (a) target changed, (b) next step is blocked by a new obstacle, (c) a shorter path opened up (check every 5 rounds)
  4. This eliminates path flip-flopping which is a major cause of oscillation
- **Success**: Oscillation count reduced by 30%+ vs T12 baseline.
- **Depends on**: T12

### T20: Package Structure Refactoring
- **Agent**: qa-agent
- **Status**: open
- **Priority**: 1
- **Files**: ALL (structural refactoring)
- **Description**: Reorganize flat file layout into proper package structure with matching test directories. See `.claude/agents/qa-agent.md` for full target layout.
  1. Create `grocery_bot/` package with `__init__.py`
  2. Move core modules (`constants.py`, `orders.py`, `pathfinding.py`, `game_state.py`, `simulator.py`) into package
  3. Create `grocery_bot/planner/` subpackage, move mixin files + `round_planner.py`
  4. Create matching test directories (`tests/planner/`, `tests/pathfinding/`, `tests/game_state/`, `tests/integration/`)
  5. Move unit tests to matching directories, integration tests to `tests/integration/`
  6. Update ALL imports (internal + tests + bot.py + benchmark.py)
  7. Verify: all tests pass, ruff clean, benchmark unchanged
- **Success**: Package structure matches qa-agent.md target. All 230+ tests pass. No score changes.
- **Depends on**: T19 (done)

### T18: Benchmark Phase 2 Changes
- **Agent**: qa-agent
- **Status**: open
- **Priority**: 7 — run after T12-T17
- **Files**: `benchmark.py`, `docs/benchmark_results.md`
- **Description**: Full benchmark and regression test update after Phase 2.
  1. Run 20-seed benchmark across all difficulties
  2. Update score regression thresholds to new baselines
  3. Profile per-round timing (must stay under 2s/round for live server)
  4. Run on live server to validate simulator results
- **Success**: All tests pass. Live server scores within 15% of simulator.
- **Depends on**: T12, T13, T14, T15, T16, T17

---

## Completed Tasks (Phase 1)

### T1: Fix Medium deadlocks (seeds 12, 13, 15)
- **Result**: Fixed. Medium avg 142.6 (was 110.3).

### T2: Wire Hungarian assignment into RoundPlanner
- **Result**: Added `assign_items_to_bots()` API to GameState.

### T3: Wire Hungarian into round decisions
- **Result**: Hungarian for bots > items, greedy for multi-slot. Hard +4.5.

### T4: Wire interleaved delivery into RoundPlanner
- **Result**: Partial delivery when near dropoff. Minimal impact.

### T5: Benchmark current state (baseline)
- **Result**: Baseline captured.

### T6: Add tests for multi-bot collision edge cases
- **Result**: 7 new tests, all pass.

### T7: Benchmark after all changes
- **Result**: Easy 152.6, Medium 104.3, Hard 76.2, Expert 45.3.

### T8: Investigate Hard/Expert score regression
- **Result**: Two fixes applied. Hard/Expert improved.

### T9: Raise score regression test thresholds
- **Result**: Thresholds updated to realistic simulator values.

### T10: Refactor round_planner.py — extract focused modules
- **Result**: Split into 6 mixin modules.

### T11: Improve simulator fidelity
- **Result**: Gap reduced to 5-8%.

### T19: Single-Responsibility Refactoring and Unit Test Coverage
- **Agent**: qa-agent
- **Status**: done
- **Result**: All 4 sub-tasks completed: (1) Eliminated 6 module globals + sync functions in bot.py, tests updated to use bot._gs.*. (2) corridor_cells was already removed from pathfinding.py. (3) Added 33 new unit tests for untested mixin/planner methods (197->230 non-slow tests). (4) Type hints added to all public signatures in 9 production files. Ruff clean, 230 tests pass.
- **Priority**: 1 (blocks all other work)
- **Files**: ALL source files + `tests/`
- **Depends on**: none

---

## Notes

- Add new tasks at the bottom of "Open Tasks" with the next T-number
- When completing a task, move it to "Completed Tasks" with a one-line result
- If a task is blocked, set status to `blocked` and note why
- **All optimization must be validated on live server** — simulator scores alone are insufficient
- **Phase 2 goal**: Expert >= 200, Hard >= 150, Medium >= 180
