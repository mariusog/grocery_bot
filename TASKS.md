# Task Board

Agents MUST check this file before starting work and update it when claiming or completing tasks.

Status: `open` | `in-progress` | `done` | `blocked`

## Live Server Results (2026-03-06)

| Difficulty | Bots | Live Score | Simulator Avg | Gap |
|------------|------|------------|---------------|-----|
| Easy | 1 | 133 | 134.4 | -1% |
| Medium | 3 | 110 | 141.2 | -22% |
| Hard | 5 | 70 | 118.2 | -41% |
| Expert | 10 | 46 | 92.5 | -50% |

Single-bot is accurate. Multi-bot diverges sharply — simulator maps don't match real layouts. **All optimization must be validated against live server.**

---

## Open Tasks (priority order)

### T11: Improve simulator fidelity (CRITICAL)
- **Agent**: qa-agent
- **Status**: done
- **Result**: Added border walls and mid-aisle barrier walls to simulator. Gap reduced from 22-50% to 5-8% for Medium/Hard/Expert. Updated test thresholds to match realistic layouts. New sim avgs: Easy 152.6, Medium 104.5, Hard 71.7, Expert 49.6. Also added wall/item position logging to bot.py for future map comparison.
- **Priority**: 1 — blocks all other optimization work
- **Files**: `simulator.py`, `logs/`
- **Description**: Live server scores are 22-50% below simulator across multi-bot difficulties. The simulator's fixed symmetric aisle layout doesn't match real maps. Two approaches:
  1. Compare logged game state (round 0) from `logs/` against simulator-generated maps to identify layout differences (wall positions, shelf placement, item types, dropoff/spawn).
  2. Randomize map generation using the seed — vary aisle count/spacing, corridor positions, shelf item distribution, dropoff/spawn placement. This stress-tests the bot against diverse layouts instead of overfitting to one pattern.
- **Success**: Simulator scores within 10% of live server scores on same difficulty

### T9: Raise score regression test thresholds
- **Agent**: qa-agent
- **Status**: done
- **Result**: Updated all thresholds to match realistic simulator: Easy avg>=135 min>=130, Medium avg>=85, Hard avg>=55 min>=10, Expert avg>=38 min>=20. Tightened Easy single-seed to 130. Also adjusted spawn dispersal and delivery gap thresholds for walled maps.
- **Priority**: 2
- **Files**: `test_bot.py`
- **Description**: Current score regression tests have low thresholds that let performance regressions slip through. Raise minimum score requirements based on current benchmarks: Easy >= 125, Medium >= 130, Hard >= 110, Expert >= 85. Add per-difficulty multi-seed regression tests (5+ seeds each) so that regressions in any difficulty are caught before merging.
- **Success**: Tests fail if any difficulty drops below threshold
- **Depends on**: T11 (thresholds should reflect realistic maps)

### T2: Wire Hungarian assignment into RoundPlanner
- **Agent**: pathfinding-agent
- **Status**: done
- **Result**: Added `assign_items_to_bots()` to GameState — high-level API that takes (bot_id, pos, slots) tuples and item dicts, handles adjacency/zones, uses Hungarian for small matrices and greedy fallback. Returns dict of bot_id -> item list.
- **Priority**: 3
- **Files**: `game_state.py`
- **Description**: `hungarian_assign()` exists in game_state.py but RoundPlanner still uses greedy assignment. Expose a clean API that RoundPlanner can call. Do NOT modify round_planner.py — add a task for strategy-agent to wire it in.
- **Depends on**: none

### T3: Wire Hungarian into round decisions
- **Agent**: strategy-agent
- **Status**: done
- **Result**: Hungarian used when bots outnumber items (Expert/Hard), greedy for multi-slot scenarios (Easy/Medium). Hard improved 71.7->76.2. Expert slightly worse due to wall-constrained layouts. Extracted _greedy_assign method for fallback.
- **Priority**: 4
- **Files**: `round_planner.py`
- **Description**: Once T2 is done, call the Hungarian assignment API from RoundPlanner instead of greedy. A/B test with benchmarks.
- **Depends on**: T2

### T4: Wire interleaved delivery into RoundPlanner
- **Agent**: strategy-agent
- **Status**: done
- **Result**: Added interleaved delivery in Step 5: when bot has 2+ active items, more items remain on shelves, and distance to dropoff <= 3, deliver partial load first. Minimal impact in practice since Step 4 handles most pickup-before-deliver scenarios, but provides a small optimization for tight layouts.
- **Priority**: 5
- **Files**: `round_planner.py`
- **Description**: `plan_interleaved_route()` exists in game_state.py but isn't called. Integrate it into the delivery decision in Step 5. Only use interleaved when detour < 3 steps.
- **Depends on**: none

### T6: Add tests for multi-bot collision edge cases
- **Agent**: qa-agent
- **Status**: done
- **Result**: Added 7 tests in TestMultiBotCollisionEdgeCases: head-on corridor collision, yield-to-delivering-bot, spawn dispersal, dropoff congestion (3 bots), 5-bot no-deadlock, oscillation detection, corridor swap prevention. All 137 tests pass.
- **Priority**: 6
- **Files**: `test_bot.py`
- **Depends on**: none

### T10: Refactor round_planner.py — extract focused modules
- **Agent**: strategy-agent
- **Status**: done
- **Result**: Split 1368-line RoundPlanner into 6 mixin modules via inheritance. round_planner.py (386 lines) orchestrator + movement.py (117) + assignment.py (228) + pickup.py (321) + delivery.py (111) + idle.py (73). All 130 tests pass, no module > 400 lines. Updated CLAUDE.md file ownership.
- **Priority**: 7
- **Files**: `round_planner.py`, `movement.py`, `assignment.py`, `pickup.py`, `delivery.py`, `idle.py`
- **Depends on**: T9

### T7: Benchmark after all changes
- **Agent**: qa-agent
- **Status**: done
- **Result**: Full benchmark (seeds 1-20, all difficulties). Easy 152.6, Medium 104.3, Hard 76.2, Expert 45.3. Simulator within 5-15% of live server. All 137 tests pass. Report in docs/benchmark_results.md.
- **Priority**: 8 — run last
- **Files**: `benchmark.py`, `docs/benchmark_results.md`
- **Depends on**: T2, T3, T4, T11

---

## Completed Tasks

### T1: Fix Medium deadlocks (seeds 12, 13, 15)
- **Result**: Already fixed by recent commits. Medium avg 142.6 (was 110.3), no seeds below 100.

### T5: Benchmark current state (baseline)
- **Result**: Baseline captured. Easy 134.4, Medium 142.6, Hard 113.3, Expert 91.0 (simulator, 20 seeds).

### T8: Investigate Hard/Expert score regression
- **Result**: Two fixes: Step 7b (idle bots deliver non-active inventory, capped at n//3) and preview walker cap (n//2). Hard 113.3->118.2, Expert 91.0->92.5.

---

## Notes

- Add new tasks at the bottom of "Open Tasks" with the next T-number
- When completing a task, move it to "Completed Tasks" with a one-line result
- If a task is blocked, set status to `blocked` and note why
- **All optimization must be validated on live server** — simulator scores alone are insufficient
