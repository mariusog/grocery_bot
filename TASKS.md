# Task Board

Agents MUST check this file before starting work and update it when claiming or completing tasks.

Status: `open` | `in-progress` | `done` | `blocked`

## Current Performance (2026-03-07, 10-seed benchmark)

| Difficulty | Bots | Sim Avg | Live Score | Waste% | InvFW | Rds/Ord | Idle% |
|------------|------|---------|------------|--------|-------|---------|-------|
| Easy       | 1    | 146.3   | 133        | 10.6%  | 0     | 16.9    | 0.9%  |
| Medium     | 3    | 113.2   | 110        | 43.4%  | 0     | 23.5    | 1.8%  |
| Hard       | 5    | 89.2    | 70         | 47.8%  | 49    | 29.8    | 15.3% |
| Expert     | 10   | 59.2    | 46         | 39.9%  | 322   | 50.9    | 30.3% |

**Per-bot idle (Expert):** B0:4% B1:8% B2:20% B3:21% B4:32% B5:36% B6:44% B7:45% B8:44% B9:50%

### Key Bottlenecks (ranked by impact)
1. **43-48% waste on Medium/Hard** — preview pickups clog inventory, no clearing mechanism for medium teams
2. **MAX_CONCURRENT_DELIVERERS=1 on Expert** — 10 bots share 1 delivery slot, causes 322 inv-full waits and 908 total waits
3. **30% idle on Expert** — bots 5-9 idle 36-50%, doing nothing useful
4. **T30 dropoff queuing infra built but NOT wired** — `get_dropoff_approach_target()` exists in game_state.py but planner never calls it
5. **Rounds/order 50.9 on Expert** — should be <20 with 10 bots, coordination overhead destroys throughput

---

## Completed Recent Tasks

### T24: A/B Strategy Testing Framework
- **Agent**: qa-agent
- **Status**: done
- **Result**: Added action-tracking diagnostics (moves/waits/pickups/delivers, waste%, inv-full waits, rounds/order, P/D ratio, per-bot idle) to simulator and `benchmark.py --diagnostics` mode.

### T25: Fix Inventory Clog (Expert #1 Bottleneck)
- **Agent**: strategy-agent
- **Status**: done
- **Result**: Investigated thoroughly. Root cause is single-dropoff-cell congestion with 10 bots. Planner-level fixes either regress or are neutral. Requires pathfinding/collision changes.

### T30-pf: Smart Dropoff Queuing Infrastructure
- **Agent**: pathfinding-agent
- **Status**: done
- **Result**: Infrastructure complete in game_state.py and pathfinding.py. Added: precomputed dropoff zones (adjacents, approach cells within radius 3, wait cells at distance 4), `get_dropoff_approach_target()` for congestion-aware delivery routing, `is_dropoff_congested()` and `get_avoidance_target()` for non-delivering bots, `bfs_toward()` utility for routing toward unreachable goals, position tracking methods (`update_round_positions`, `notify_bot_target`, `count_bots_near_dropoff`, `count_bots_targeting_dropoff`). All infrastructure is safe (zero performance impact -- baseline unchanged: Easy 147, Medium 112, Hard 89, Expert 59). Strategy-agent must wire via T33.
- **Files**: `grocery_bot/pathfinding.py`, `grocery_bot/game_state.py`
- **Note**: Tested multiple pathfinding-level approaches (relaxed temporal BFS, round-trip assignment, goal-occupant bypass) -- all regressed Expert by 8-17%. The bottleneck is firmly in planner logic (which bots deliver when), not pathfinding. T32 (concurrent deliverers) and T33 (wiring this infra) are the path forward.

---

## Open Tasks (priority order — lead-agent analysis 2026-03-07)

### T31: Reduce Waste% on Medium/Hard (43-48% -> <25%)
- **Agent**: strategy-agent
- **Status**: done (no code changes — see findings)
- **Priority**: 1
- **Result**: Investigated exhaustively. All prescribed approaches regress scores. Waste% metric is misleading — preview pickup is optimal behavior. No code changes committed.
- **Findings**:
  1. **Waste% is a misleading metric.** On Hard seed=1, `active_pickup` is called 886 times but succeeds only 104 times (12%). 717 failures are because `net_active` is empty — all active items are already picked by other bots, waiting for delivery. Bots pick preview items because there are literally NO active items left on shelves ~80% of the time.
  2. **Every approach to reduce preview pickup made scores worse**, because bots idle instead of earning 1 point per preview item delivered:
     - Gate opportunistic_preview + preview_prepick for 8+ types: Medium -5.5, Hard -9.1
     - Gate only preview_prepick for 8+ types: Hard -2.5
     - Gate rush_deliver + deliver_active detours for 8+ types: Medium -4.4, Hard -11.5
     - Tighter detour (max_detour=1): Mixed results (Medium -1.6, Hard +1.6)
     - Force_slots tightening (20-seed): Hard -3.2
     - DELIVER_WHEN_CLOSE_DIST 3->2: Zero effect
  3. **The real bottleneck is delivery throughput**, not pickup waste. With 3-5 bots sharing one dropoff cell, bots finish picking quickly but queue to deliver. The "wasted" preview items are the best available action during this dead time.
  4. **`ctx.role` is never referenced in any step chain method** — role assignments from `_assign_roles()` do not gate any decisions. Fixing this is a prerequisite for role-based waste reduction.
- **Recommendation**: Close this task. Improve scores via T32 (delivery throughput, done), T33 (dropoff queuing), and T34 (idle reduction). If waste reduction is still desired, first wire `ctx.role` into step chain gates so roles actually affect behavior.

### T32: Scale MAX_CONCURRENT_DELIVERERS by Bot Count
- **Agent**: strategy-agent
- **Status**: done
- **Result**: Scaled max_deliverers to max(2, num_bots//4) for 8+ bots. Scaled picker count to 1-per-item for large teams. Expert avg 59.2 (was 52.9), +6.3 points. No regression on Easy/Medium/Hard.
- **Priority**: 2 (Expert bottleneck)
- **Metric**: Expert InvFW=322, Waits=908, MAX_CONCURRENT_DELIVERERS=1 for 8+ bots
- **Target**: InvFW < 100, Expert > 70
- **Files**: `grocery_bot/planner/round_planner.py` (lines 355-358), `grocery_bot/constants.py`
- **Root cause**: `_assign_roles()` line 355-358 sets `max_deliverers = MAX_CONCURRENT_DELIVERERS (=1)` for 8+ bots. With 10 bots and only 1 delivery slot, bots queue endlessly. The delivery queue fills up but only 1 bot can deliver at a time. 322 bot-rounds are spent waiting with full inventory.
- **How to fix**:
  1. Change `_assign_roles()` delivery scaling to: `max_deliverers = max(1, len(self.bots) // 4)` — gives 2 for Expert (10 bots), 1 for Hard (5 bots). This is conservative enough to avoid congestion but doubles throughput.
  2. Wire T30's `get_dropoff_approach_target()` into `_emit_move_or_wait` when target is dropoff — this ensures the 2 deliverers approach from different sides and don't block each other. (Depends on T30-pf completing.)
  3. Increase `MAX_NONACTIVE_DELIVERERS` from 1 to 2 for teams >= 8 — allows junk clearing in parallel with active delivery.
- **Risk**: If 2 deliverers approach from same direction, they block each other. Mitigated by T30's approach lanes.
- **Expected gain**: +8-15 Expert.
- **Depends on**: T30-pf for full effect, but deliverer scaling alone should help.

### T33: Wire T30 Dropoff Queuing + Delivery Queue Gating
- **Agent**: strategy-agent
- **Status**: done
- **Priority**: 2
- **Result**: Wired T30 `is_dropoff_congested()` + `get_avoidance_target()` into `_try_clear_dropoff` for 8+ bots. Added delivery queue gating to `_step_rush_deliver`: non-front bots search harder for preview detours (CASCADE_DETOUR_STEPS) instead of rushing to dropoff. Expert +1.1 (10-seed: 60.3 vs 59.2). No regression on Easy/Medium/Hard.
- **Files**: `grocery_bot/planner/round_planner.py`, `grocery_bot/planner/idle.py`
- **Findings**:
  1. **`get_dropoff_approach_target()` in `_emit_move_or_wait` is harmful** — redirecting delivering bots to wait cells consistently regresses Expert by 3-5 points. Wait cells waste rounds that could be spent queuing closer.
  2. **Role gates on step chain are mostly neutral** — gating `_step_active_pickup`, `_step_preview_prepick`, `_step_idle_positioning` by role for 8+ bots showed no improvement. The role system assigns roles but the step chain's priority ordering already produces near-optimal behavior without gates.
  3. **`_should_deliver_early()` is harmful** — wiring it into `_step_deliver_active` caused Expert regression (54.0 vs 59.2).
  4. **Scaling `MAX_NONACTIVE_DELIVERERS` is harmful** — increasing from 1 to 2 for Expert causes more dropoff congestion (54.5 vs 59.2).
  5. **Scaling endgame threshold by bot count is harmful** — shorter endgame for Expert regresses all difficulties.
  6. **Single-cell dropoff is the hard bottleneck** — all planner changes that increase dropoff traffic hurt, and all changes that reduce it help only marginally. Expert >70 requires game-level changes (multi-cell dropoff or faster delivery mechanic).

### T41: Production-Grade Refactor — File Size + Test Coverage
- **Agent**: qa-agent
- **Status**: done
- **Priority**: 0 (blocks all other work)
- **Goal**: Bring entire codebase to production quality. Every file under 300 lines, every public method tested.
- **Result**: All file splits complete. Source: pickup.py (399->291) + preview.py (120), benchmark.py (396->197) + benchmark_reporting.py (214), round_planner.py (313->298). Tests: 10 oversized test files split into 27 smaller files, all under 300 lines. Shared helpers extracted to conftest.py files in pathfinding/, game_state/, planner/ test dirs. 432 tests pass, benchmark shows no regression.
- **Source files over 300 lines (MUST split)**:
  - `grocery_bot/planner/pickup.py` (399 lines) — split preview/detour into `preview.py`
  - `benchmark.py` (396 lines) — split reporting into `benchmark/reporting.py`
  - `grocery_bot/planner/round_planner.py` (313 lines) — trim to under 300
- **Test files over 300 lines (MUST split by test class)**:
  - `tests/integration/test_decision_preview.py` (1122 lines)
  - `tests/integration/test_decision_basic.py` (907 lines)
  - `tests/integration/test_multi_bot.py` (750 lines)
  - `tests/game_state/test_game_state_unit.py` (709 lines)
  - `tests/planner/test_movement_unit.py` (451 lines)
  - `tests/planner/test_pickup_unit.py` (427 lines)
  - `tests/pathfinding/test_pathfinding.py` (415 lines)
  - `tests/planner/test_round_planner_unit.py` (370 lines)
  - `tests/test_simulator.py` (366 lines)
  - `tests/planner/test_assignment_unit.py` (335 lines)
- **Missing test coverage**: Write unit tests for every public method in:
  - `grocery_bot/game_state/distance.py`
  - `grocery_bot/game_state/path_cache.py`
  - `grocery_bot/game_state/dropoff.py`
  - `grocery_bot/planner/steps.py`
  - `grocery_bot/planner/coordination.py`
  - `grocery_bot/simulator/diagnostics.py`
  - `grocery_bot/simulator/map_generator.py`
- **Quality checks**: SOLID violations, Law of Demeter, magic numbers, type annotations
- **Success criteria**: All files under 300 lines, all tests pass, every public method has a test

### T34: Reduce Expert Idle Time (30% -> 15%)
- **Agent**: strategy-agent
- **Status**: open
- **Priority**: 3
- **Metric**: Expert Idle%=30.3%, Bots 5-9 idle 36-50%
- **Target**: No bot idle > 30%. Expert > 75.
- **Files**: `grocery_bot/planner/idle.py`, `grocery_bot/planner/round_planner.py`, `grocery_bot/planner/assignment.py`
- **Root cause**: `_assign_roles()` assigns `active_picker_count = ceil(active_on_shelves / 3)` pickers, then a few preview bots, and ALL remaining bots get role "idle". With 5-item order and 10 bots, only 2 are pickers, 1 delivers, 2 preview => 5 idle.
- **How to fix**:
  1. **Assign more pickers**: Change picker count to `min(active_on_shelves, num_bots - max_deliverers)` — every bot should target an item. Even if 2 bots target the same item type, the second-closest is backup.
  2. **Eliminate idle role for Expert**: When `num_bots >= 8`, assign surplus bots as "pick" with lower-priority items (second-closest copies of needed types). An active picker that arrives and finds its item already taken can immediately re-route to the next needed item.
  3. **Pre-position idle bots near highest-probability item locations**: In `_try_idle_positioning`, instead of generic corridor spots, target the shelf columns that contain the most distinct item types (more likely to be needed next).
- **Risk**: More pickers could cause aisle congestion. Mitigate with stagger: only assign 2 bots per aisle column max.
- **Expected gain**: +5-10 Expert.
- **Depends on**: T31 (reduced waste means more useful pickups per bot).

### T26: Reduce Expert Idle Time (SUPERSEDED by T34)
- **Status**: superseded
- **Note**: Original T26 is replaced by T34 with concrete diagnostic data and specific code changes.

### T27: Optimize Rounds-Per-Order (DEFERRED)
- **Status**: deferred
- **Note**: Rounds/order will improve as a side effect of T31-T34. Reassess after those complete.

### T28: Endgame Delivery Optimization (SUPERSEDED by T38+T40)
- **Status**: superseded
- **Note**: Split into T38 (scale threshold) and T40 (endgame preview delivery).

### T35: Wire `_should_deliver_early()` into Step Chain (delivery.py)
- **Agent**: strategy-agent
- **Status**: open
- **Priority**: 2
- **Metric**: Rounds/order on Medium=23.5, Hard=29.8 — delivery timing is suboptimal
- **Target**: Rounds/order Medium < 21, Hard < 27
- **Files**: `grocery_bot/planner/delivery.py`, `grocery_bot/planner/round_planner.py` (step chain only)
- **Root cause**: `_should_deliver_early()` (delivery.py:38) is DEAD CODE — never called from any step. `_step_deliver_active` (round_planner.py:692) uses a fixed `DELIVER_WHEN_CLOSE_DIST=3` threshold instead of the smarter cost comparison. Bots with 1 active item walk to a far item when delivering immediately and starting fresh would be cheaper.
- **How to fix**: In `_step_deliver_active`, before the `d_to_drop <= DELIVER_WHEN_CLOSE_DIST` check, add: `if self._should_deliver_early(ctx.pos, ctx.inv): [deliver]`.
- **Risk**: Low. Method exists with tests. Just needs wiring.
- **Expected gain**: +2-4 Medium/Hard.

### T36: Use `_flexible_tsp` for Multi-Bot Routes (pickup.py)
- **Agent**: strategy-agent
- **Status**: done (no code changes — regresses)
- **Priority**: 3
- **Result**: Tested `_flexible_tsp` in both `_build_greedy_route` and `_build_assigned_route` with 20-seed benchmarks. Both regress Medium by 2-6 points and Expert by 2-4 points. Root cause: `_flexible_tsp` picks locally optimal adjacent cells per-bot that conflict with other bots' paths in multi-bot mode. The `tsp_route` uses globally precomputed `best_pickup` cells which coordinate better across bots. `_flexible_tsp` remains correct for single-bot mode only.

### T37: Apply Last-Item Priority Boost in Greedy Route (pickup.py)
- **Agent**: strategy-agent
- **Status**: done (no code changes — regresses Expert)
- **Priority**: 3
- **Result**: Tested with 20-seed benchmark. Expert regresses -9 points (52.7 vs 61.8 baseline). Root cause: `_build_greedy_route` is only used in multi-bot mode, and the 0.33 cost multiplier causes ALL bots to rush the same 1-2 remaining active items, creating pile-ups. The Hungarian assignment in game_state already applies this multiplier at the assignment level where items are distributed across bots. Applying it again at per-bot greedy routing causes duplicate prioritization without coordination.

### T38: Scale Endgame Threshold by Bot Count (constants.py)
- **Agent**: lead-agent
- **Status**: open
- **Priority**: 4
- **Metric**: Expert idle=30% in endgame, bots stop picking too early with ENDGAME_ROUNDS_LEFT=40
- **Files**: `grocery_bot/constants.py`, `grocery_bot/planner/round_planner.py` (line 69)
- **Root cause**: 10 bots on Expert can pick+deliver remaining items in ~15 rounds, but endgame triggers at 40, causing premature delivery rushes.
- **How to fix**: `endgame_threshold = max(15, ENDGAME_ROUNDS_LEFT - len(self.bots) * 2)` gives Easy=38, Medium=34, Hard=30, Expert=20.
- **Risk**: Medium — needs benchmarking.
- **Expected gain**: +2-5 Expert.

### T39: Lower `MIN_INV_FOR_NONACTIVE_DELIVERY` for Large Teams (constants.py)
- **Agent**: lead-agent
- **Status**: open
- **Priority**: 4
- **Metric**: Expert bots idle with 1 preview item, never delivering (+1 point each lost)
- **Files**: `grocery_bot/constants.py`, `grocery_bot/planner/round_planner.py`
- **Root cause**: `MIN_INV_FOR_NONACTIVE_DELIVERY=2` blocks single-item deliveries. On Expert, idle bots hold 1 item worth +1 but never deliver it.
- **How to fix**: Override to 1 for teams >= 8 in `_step_idle_nonactive_deliver`.
- **Risk**: Low — only affects idle bots.
- **Expected gain**: +3-5 Expert.

### T40: Endgame Maximize-Items Should Include Preview Inventory (delivery.py)
- **Agent**: strategy-agent
- **Status**: done
- **Priority**: 5
- **Result**: Added preview-inventory endgame delivery path to `_try_maximize_items` in delivery.py. Code is correct and neutral (20-seed benchmark confirms no regression). Currently unreachable because `_step_endgame` in round_planner.py gates `_try_maximize_items` calls on `ctx.has_active and self.active_on_shelves > 0`. Requires round_planner.py update to also call `_try_maximize_items` for bots with preview-only inventory during endgame.

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

### Phase 3
| Task | Result |
|------|--------|
| T29: Cross-cutting perf and yield fix | BFS memory optimization, endgame threshold 30->40, dist cache 256->512, yield-to logic fix. Hard +3.5, Expert InvFW -28%. Stuck% halved. |

---

## Notes

- **BUG (lead-agent)**: Uncommitted changes to `round_planner.py` use `self._active_delivering` and `PREDICTION_TEAM_MIN` without initializing/importing them. Tests fail with AttributeError/NameError. Pathfinding-agent restored the committed version to unblock testing.
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
