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

### T33: Wire T30 Dropoff Queuing into Planner
- **Agent**: strategy-agent
- **Status**: blocked (waiting on T30-pf)
- **Priority**: 2
- **Metric**: Expert Waits=908, Stuck%=0.1% (low but waits are high)
- **Target**: Expert Waits < 500
- **Files**: `grocery_bot/planner/movement.py`, `grocery_bot/planner/round_planner.py`
- **Root cause**: `game_state.py` has `get_dropoff_approach_target()`, `is_dropoff_congested()`, and `get_avoidance_target()` but the planner NEVER calls them. All bots target dropoff directly, causing pile-ups.
- **How to fix**:
  1. In `_emit_move_or_wait`: when target == self.drop_off and len(self.bots) >= 8, call `gs.get_dropoff_approach_target(bid, pos, drop_off, delivering_bots)` to get a staged target. If `should_wait`, path to wait cell instead of dropoff.
  2. In `_step_clear_dropoff`: when `gs.is_dropoff_congested(drop_off, bot_positions)`, non-delivering bots call `gs.get_avoidance_target()` and move away.
  3. Collect `delivering_bots` list during `_update_delivery_queue` — it already tracks who's delivering.
- **Risk**: Over-staging could slow delivery. Start conservative: only trigger for 8+ bots.
- **Expected gain**: +5-10 Expert (combined with T32).
- **Depends on**: T30-pf (pathfinding-agent) completing first.

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

### T28: Endgame Delivery Optimization
- **Agent**: strategy-agent
- **Status**: open
- **Priority**: 4
- **Files**: `grocery_bot/planner/delivery.py`, `grocery_bot/planner/round_planner.py`
- **Description**: Tune endgame threshold based on bot count and distance to dropoff. Currently triggers at 40 rounds remaining.
- **Depends on**: T31, T32

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
