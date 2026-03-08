# Task Board

Agents MUST check this file before starting work and update it when claiming or completing tasks.

Status: `open` | `in-progress` | `done` | `blocked`

## Current Performance (2026-03-08, 10-seed synthetic + replay maps)

**Synthetic benchmark** (`python benchmark.py --synthetic --seeds 10 --diagnostics`):

| Difficulty | Bots | Avg | Min | Max | StdDev | Waste% | Rds/Ord | Idle% | AvgDel |
|------------|------|-----|-----|-----|--------|--------|---------|-------|--------|
| Easy       | 1    | 148.5 | 138 | 153 | 6.0 | 13.7% | 16.7 | 1.2% | 2.98 |
| Medium     | 3    | 154.3 | 119 | 178 | 16.4 | 56.5% | 17.2 | 7.0% | 2.36 |
| Hard       | 5    | 136.3 | 111 | 154 | 11.8 | 61.1% | 19.5 | 23.8% | 1.86 |
| Expert     | 10   | 108.6 | 97 | 133 | 11.5 | 61.4% | 27.3 | 45.4% | 1.82 |
| Nightmare  | 20   | 82.5 | 1 | 215 | 71.8 | 55.7% | 36.1 | 80.6% | 1.83 |

**Replay benchmark** (`python benchmark.py`):

| Map | Bots | Grid | Score |
|-----|------|------|-------|
| 12x10_1bot | 1 | 12x10 | 126 |
| 16x12_3bot | 3 | 16x12 | 142 |
| 22x14_5bot | 5 | 22x14 | 112 |
| 28x18_10bot | 10 | 28x18 | 104 |
| 30x18_20bot | 20 | 30x18 | 151 |

**Per-bot util (Expert 10-seed):** B0:95% B1:87% B2:80% B3:67% B4:61% B5:50% B6:32% B7:32% B8:28% B9:15%
**Per-bot util (Nightmare 10-seed):** Highly variable (StdDev=71.8). Best seeds use ~6 bots; worst seeds score 1 point.

### Key Bottlenecks (ranked by impact — updated 2026-03-08 from Nightmare analysis)
1. **Assignment system doesn't scale** — On Nightmare (20 bots), 12/20 bots never pick up a single item across 500 rounds. The planner assigns work to 5-6 nearest bots and leaves 14 permanently idle. See T34, T49.
2. **Spawn gridlock** — All bots spawn at a single cell (28,16). With 20 bots, only 1-2 can move per round → 75 rounds wasted just dispersing. See T49.
3. **Oscillation at scale** — Bot 0 (top performer, 93% util) oscillates (4,15)↔(4,16) for 150+ rounds (R345-R496) carrying 2 items. The idle positioning logic bounces bots between adjacent cells when no clear assignment exists. See T50.
4. **Bot processing order is arbitrary** — `round_planner.py:113` iterates in server order, not urgency. See T42.
5. **`_spare_slots` blocks preview pickups globally** — reserves slots for active items across ALL bots. See T43.
6. **80.8% idle on Nightmare, 30% on Expert** — most bots have nothing to do. See T34.
7. **Single-cell dropoff is the hard bottleneck** — T33 confirmed all planner changes that increase dropoff traffic hurt.
8. ~~43-48% waste on Medium/Hard~~ — T31 confirmed waste% is misleading; preview pickup is optimal behavior.
9. ~~MAX_CONCURRENT_DELIVERERS=1~~ — Fixed by T32 (scaled to max(2, bots//4)).

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

### T34: Reduce Idle Time (Expert 30%→15%, Nightmare 80%→40%)
- **Agent**: strategy-agent
- **Status**: open
- **Priority**: 1
- **Metric**: Expert Idle%=30.3% (B5-B9 idle 36-50%). Nightmare Idle%=80.8% (12/20 bots never pick up anything).
- **Target**: No bot idle > 30%. Expert > 75. Nightmare > 200.
- **Files**: `grocery_bot/planner/idle.py`, `grocery_bot/planner/round_planner.py`, `grocery_bot/planner/assignment.py`
- **Root cause**: `_assign_roles()` assigns `active_picker_count = ceil(active_on_shelves / 3)` pickers, then a few preview bots, and ALL remaining bots get role "idle". With 6-item order and 20 bots, only 2 are pickers, 1-5 deliver, 2 preview ⇒ 11-15 idle. The assignment system never gives far-away bots anything to do.
- **How to fix**:
  1. **Assign more pickers**: Change picker count to `min(active_on_shelves, num_bots - max_deliverers)` — every bot should target an item. Even if 2 bots target the same item type, the second-closest is backup.
  2. **Eliminate idle role for large teams**: When `num_bots >= 8`, assign surplus bots as "pick" with lower-priority items (second-closest copies of needed types). An active picker that arrives and finds its item already taken can immediately re-route to the next needed item.
  3. **Pre-stage idle bots near preview-order items**: In `_try_idle_positioning`, position empty idle bots near known preview-order item shelf locations (not generic corridor spots). When the order transitions, these bots can start picking immediately instead of traversing the map. The `_preview_stage_weight` in idle.py only works for bots carrying preview items — extend to empty bots too.
  4. **Distribute work across map regions**: On Nightmare, items span the full 30-wide grid but only bots near the left side (close to dropoff) get assigned. Assign far-side bots to far-side items — even though delivery takes longer, it's better than 0 contribution.
- **Risk**: More pickers could cause aisle congestion. Mitigate with stagger: only assign 2 bots per aisle column max.
- **Expected gain**: +5-10 Expert, +30-50 Nightmare.
- **Depends on**: T49 (bots must disperse from spawn first).

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
- **WARNING**: T33 finding #3 shows this REGRESSES Expert (54.0 vs 59.2). May need to gate by team size — only apply for teams < 8.

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
- **WARNING**: T33 finding #5 says "scaling endgame threshold by bot count is harmful — shorter endgame for Expert regresses all difficulties." May need a different approach (e.g. smarter endgame behavior rather than shorter window).

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

### T42: Sort Bot Processing by Urgency Order (round_planner.py)
- **Agent**: strategy-agent
- **Status**: done (no code changes — regresses all difficulties)
- **Priority**: 1
- **Result**: Tested urgency-sorted bot processing with 20-seed benchmarks. Regresses all multi-bot difficulties: Hard -9.6 (124.3 vs 133.9), Expert -20.8 (89.4 vs 110.2), Nightmare -39.6 (103.2 vs 142.8). Also tested yielding to predicted positions of already-decided higher-urgency bots — still regresses Expert by 6.3 (103.9 vs 110.2).
- **Findings**:
  1. **Processing order affects `predicted` (hard blocks) while `_yield_to` affects `_emit` (soft redirects).** When delivering bots are processed first, they claim `predicted` positions along their delivery paths. Picker bots processed later find cells hard-blocked and must take longer routes or wait.
  2. **The current system (server order + `_yield_to`) is cooperative scheduling.** Pickers plan routes first, then soft-yield at emission time when they'd collide with higher-urgency bots. This is cheaper than hard-blocking paths.
  3. **Single-cell dropoff amplifies the problem.** Delivering bots all route toward the same dropoff cell. When they go first, they block the main corridors. Pickers need those corridors to reach item aisles.
  4. **`_yield_to` with urgency sorting becomes redundant.** With sorted processing, higher-urgency bots are already decided when lower-urgency bots are processed, so the `_yield_to` set (which excludes decided bots) is always empty — removing the soft collision avoidance entirely.
- **Recommendation**: The current architecture is near-optimal for bot ordering. Future improvements should focus on reducing the number of bots competing for the same paths (T34, T49) rather than reordering processing.

### T44: Split movement.py (417 lines → ≤300)
- **Agent**: strategy-agent
- **Status**: open
- **Priority**: 0 (quality gate)
- **Root cause**: `MovementMixin` is 399 lines with three 30+ line methods (`_pre_predict` at 104 lines, `_bfs_smart` at 63, `_emit` at 36). The class has collision avoidance, BFS dispatch, and move emission — at least two responsibilities.
- **How to fix**: Extract collision/prediction logic (`_pre_predict`, `_yield_to_positions`, path planning) into `collision.py`. Keep BFS dispatch and move emission in `movement.py`.
- **Files**: `grocery_bot/planner/movement.py`

### T45: Split round_planner.py (395 lines → ≤300)
- **Agent**: strategy-agent
- **Status**: open
- **Priority**: 0 (quality gate)
- **Root cause**: `RoundPlanner` is 346 lines with `plan()` at 51 lines, `_allocate_carried_need` at 47, `_compute_needs` at 36. The class mixes orchestration with need computation.
- **How to fix**: Extract `_allocate_carried_need`, `_compute_needs`, `_iter_needed_items`, and `_spare_slots` into a `needs.py` mixin. Keep `plan()` and `_decide_bot()` in `round_planner.py`.
- **Files**: `grocery_bot/planner/round_planner.py`

### T46: Split bot.py (618 lines → ≤300)
- **Agent**: lead-agent
- **Status**: open
- **Priority**: 0 (quality gate)
- **Root cause**: `bot.py` has 618 lines with `play()` at 224 lines. It mixes WebSocket loop, action validation, game logging, map recording, and API functions.
- **How to fix**: Extract `_validate_actions`, `_update_expected_positions`, `_update_expected_inventories` into `validation.py`. Extract `_build_map_snapshot`, `_save_recorded_map`, `_build_game_meta`, `_log_round`, `_log_game_over` into `logging_utils.py`. Keep `play()` and the API functions in `bot.py`.
- **Files**: `bot.py`

### T47: Centralize Module-Level Constants into constants.py
- **Agent**: lead-agent
- **Status**: done
- **Priority**: 1 (quality)
- **Result**: Moved 12 constants from 5 modules into `constants.py`. Updated imports in `dropoff.py`, `distance.py`, `path_cache.py`, `pathfinding.py`, `runner.py`, and `game_state/__init__.py`. Added `BFS_MAX_CELLS`, `TEMPORAL_BFS_MAX_CELLS`, `DIAG_*` thresholds. All 544 tests pass, no benchmark regression. Deferred: `max(2, num_bots // 4)` deliverer scaling dedup in `steps.py`/`coordination.py` (strategy-agent files, active worktrees).
- **Files**: `grocery_bot/constants.py` and all affected modules

### T48: Add Type Annotations to bot.py and simulator/
- **Agent**: qa-agent (simulator/), lead-agent (bot.py)
- **Status**: open
- **Priority**: 2 (quality)
- **Root cause**: ~40 functions missing param and/or return type annotations, concentrated in `bot.py` (19 functions) and `grocery_bot/simulator/` (10+ functions). Also `planner/steps.py` has 15 step methods with untyped `ctx` parameter.
- **Files**: `bot.py`, `grocery_bot/simulator/*.py`, `grocery_bot/planner/steps.py`

### T49: Spawn Dispersal for Large Teams (20+ bots)
- **Agent**: strategy-agent
- **Status**: open
- **Priority**: 1
- **Metric**: Nightmare wastes ~75 rounds dispersing 20 bots from a single spawn cell (28,16). Only 1-2 bots can move per round due to collision. By round 50, score is still 3.
- **Files**: `grocery_bot/planner/movement.py`, `grocery_bot/planner/idle.py`
- **Root cause**: All bots spawn stacked at the same cell. The planner doesn't have special spawn-phase logic — bots compete for the same movement directions, most wait. First order completion (O1) doesn't happen until R63.
- **How to fix**:
  1. **Directional fan-out from spawn**: On round 0-5, assign each bot a unique dispersal direction based on `bot_id % 4` (up/down/left/right). Stagger movement so bot 0 moves first, bot 1 waits 1 round, etc.
  2. **Pre-assign initial targets**: Instead of all bots computing the same closest item, use the Hungarian assignment immediately at round 0 to spread bots across different items/regions.
  3. **Spawn corridor clearing**: Bots without assignments should move to pre-computed corridor positions away from spawn, clearing the way for assigned bots.
- **Risk**: Low — only affects first ~20 rounds. No regression on small teams (1-5 bots disperse in 1-2 rounds).
- **Expected gain**: +10-20 Nightmare (reclaiming 50+ wasted rounds).

### T50: Fix Oscillation in Idle Positioning
- **Agent**: strategy-agent
- **Status**: in-progress
- **Priority**: 1
- **Metric**: Bot 0 on Nightmare oscillates (4,15)↔(4,16) for 150+ rounds (R345-R496) carrying 2 items. Bot 0 also oscillated (1,12)↔(1,13) for 30 rounds (R90-R118). The oscillation detector in `analyze_replay.py` finds 112 problems.
- **Files**: `grocery_bot/planner/idle.py`, `grocery_bot/planner/movement.py`
- **Root cause**: When a bot has inventory but no clear delivery or pickup target, `_try_idle_positioning` sends it toward a corridor position. But the next round, a different step (e.g., `_step_deliver_active` or `_step_preview_prepick`) sends it the opposite way. The two steps alternate control, causing the bot to bounce between two cells indefinitely.
- **How to fix**:
  1. **Oscillation detection in planner**: Track each bot's last 4 positions. If `pos[t] == pos[t-2]` for 3+ consecutive rounds, force the bot to commit to its current direction for 5 rounds (sticky decision).
  2. **Idle positioning hysteresis**: In `_try_idle_positioning`, don't change target if the bot is already moving toward a valid idle position and hasn't arrived yet.
  3. **Deliver-or-hold decision**: A bot carrying items with no active assignment should deliver immediately (even partial inventory) rather than oscillate. On Nightmare, Bot 0 holds `[juice;sugar]` for 150 rounds — delivering would score +2 and free it for new work.
- **Risk**: Low — oscillation is pure waste. Any action beats bouncing.
- **Expected gain**: +5-15 Nightmare, +2-5 Expert.

### T43: Fix `_spare_slots` Over-Conservatism (round_planner.py)
- **Agent**: strategy-agent
- **Status**: open
- **Priority**: 2
- **Metric**: Preview pickups blocked even when other bots handle all active items. Bots idle with empty inventory instead of pre-picking.
- **Files**: `grocery_bot/planner/round_planner.py` (line 366-367)
- **Root cause**: `_spare_slots(inv)` returns `(MAX_INVENTORY - len(inv)) - self.active_on_shelves`. This globally reserves slots for `active_on_shelves` items across ALL bots. Example: 2 active items on shelves, Bot A has 1 item → `spare = (3-1)-2 = 0`. Bot A is blocked from preview pickup even if Bot B and Bot C are already assigned to those 2 active items.
- **How to fix**: Account for per-bot assignment. If this bot has no active assignment (or its assigned items are already picked), don't subtract `active_on_shelves`:
  ```python
  def _spare_slots(self, inv: list[str], bid: int = -1) -> int:
      my_active = len(self.bot_assignments.get(bid, []))
      reserve = min(self.active_on_shelves, max(0, my_active))
      return (MAX_INVENTORY - len(inv)) - reserve
  ```
  Bots assigned to active items still reserve slots; unassigned bots can freely preview-pick.
- **Risk**: Medium — over-picking preview items could clog inventory. Gate by team size if needed.
- **Expected gain**: +3-8 on Medium/Hard (more preview pipelining, fewer idle rounds).
- **Depends on**: T42 (urgency ordering ensures active pickers still get priority).

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
| T41-cov: Test coverage gap audit (2026-03-08) | Added 58 tests across 5 new files: path_cache (14), diagnostics (20), map_generator (16), coordination (6), distance (2). 544 total tests, all passing. |
| T41-audit: SOLID/quality audit (2026-03-08) | Full audit: 19 magic numbers, 10 LoD violations, ~40 missing type annotations, 35 long methods, 9 large classes, 3 oversized files. Filed T44-T48 for fixes. |

### Phase 3
| Task | Result |
|------|--------|
| T29: Cross-cutting perf and yield fix | BFS memory optimization, endgame threshold 30->40, dist cache 256->512, yield-to logic fix. Hard +3.5, Expert InvFW -28%. Stuck% halved. |

---

## Nightmare Deep-Dive (seed=42, 2026-03-08)

- 12/20 bots (B7-B19) never picked up a single item in 500 rounds
- Bot 0 (93% util) oscillates (4,15)↔(4,16) for 150+ rounds (R345-R496)
- First order doesn't complete until R63 (spawn dispersal takes ~50 rounds)
- Only B0-B5 do useful work; B6 picks up 1 item total
- MaxGap=192 rounds without scoring, AvgDel=1.81 items per delivery
- 3-bot game is 9.5x more efficient per bot-round than 20-bot

## Replay Analyzer Usage

Use `analyze_replay.py` to debug game runs. **Agents MUST use this tool after any benchmark run with `--diagnostics` to verify changes.**

```sh
# List available logs
python analyze_replay.py --list

# Full summary + auto-detected problems (run this first)
python analyze_replay.py <log>

# ASCII grid at a specific round (use to inspect bot positions)
python analyze_replay.py <log> --grid 50

# Bot timeline (condensed action history with streak compression)
python analyze_replay.py <log> --bot 3

# Round-by-round detail for a range (use after finding a problem round)
python analyze_replay.py <log> --rounds 40-60

# Only auto-detected problems (idle streaks, oscillation, delivery gaps)
python analyze_replay.py <log> --problems
```

**Validation workflow for optimization tasks:**
1. Run `python benchmark.py --synthetic -d Nightmare --quick --diagnostics` (or other difficulty)
2. Run `python analyze_replay.py --list` to find the new log
3. Run `python analyze_replay.py <log>` to check summary + problems
4. Compare problem count and idle% before/after your change
5. Use `--bot <id>` and `--grid <round>` to drill into specific regressions

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
