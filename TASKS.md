# Task Board

Agents MUST check this file before starting work and update it when claiming or completing tasks.

Status: `open` | `in-progress` | `done` | `blocked`

## Current Performance (2026-03-10)

**Replay benchmark** (`python benchmark.py`, total=820 single-map):

| Map | Bots | Grid | Score |
|-----|------|------|-------|
| Easy | 1 | 12x10 | 125 |
| Medium | 3 | 16x12 | 159 |
| Hard | 5 | 22x14 | 113 |
| Expert | 10 | 28x18 | 106 |
| Nightmare | 20 | 30x18 | 317 |
| **Total** | | | **820** |

**Target: 1000 live total**

### Diagnostics Summary (from local replay logs)

| Difficulty | Rds/Order | InvFull | Waste% | Top Problem |
|------------|-----------|---------|--------|-------------|
| Medium (3-bot) | 18.8 | 8 | 47% | 34-round first-order delay |
| Hard (5-bot) | 23.1 | 80 | 68% | Bot4 waited 41 rds with full inv |
| Expert (10-bot) | 30.0 | 258 | 75% | B8-B9 waited 50+ rds with full inv |
| Nightmare (20-bot) | 15.2 | 36/bot | — | B16-B19 util 23-67%, B19 idle 103 rds |

### Key Insight: Where to Find +151 Points

1. **Medium/Hard order speed** (+50-60): We complete 16/13 orders in 300 rounds. Bitflip does ~21/25. Each extra order = ~9 points (5 bonus + 4 items). 5 more orders across Med+Hard = +45.
2. **Hard InvFull clearing** (+10-20): 5-bot teams require full inventory (3 items) before clearing non-active. Lowering to 2 saves ~40 bot-rounds of waste.
3. **Expert InvFull** (+10-20): 258 bot-rounds wasted. Scaled dropoff radius helped; further work on oscillation reduction.
4. **Nightmare tail bots** (+20-40): B16-B19 barely contribute. Better work distribution could add 20+ points.

---

## Priority Tasks (path to 1000 points)

### T61: Rounds-Per-Order Threshold Integration Tests
- **Status**: open
- **Priority**: 0 (infrastructure — do first)
- **Difficulty**: Easy (1-2 hours)
- **Files**: `tests/test_replay_regression.py`
- **Goal**: Add replay-based threshold tests for rounds-per-order and InvFull waits, similar to existing minimum score tests. These give us a fast TDD feedback loop: set a target threshold, make code changes, and verify the threshold passes without regressing other difficulties.
- **How to implement**:
  1. Add `test_rounds_per_order_bounded` to `TestReplayMinimumScores` — assert `avg_rounds_per_order` stays below per-difficulty ceilings:
     ```python
     MAX_ROUNDS_PER_ORDER = {1: 25, 3: 20, 5: 25, 10: 35, 20: 20}
     ```
  2. Add `test_inv_full_waits_bounded` — assert `inv_full_waits` stays below per-difficulty ceilings:
     ```python
     MAX_INV_FULL_WAITS = {1: 20, 3: 30, 5: 100, 10: 300, 20: 500}
     ```
  3. Start with generous thresholds (current values + 20% headroom), then tighten as T59/T60/T43 land improvements.
- **Why**: Each optimization task (T59, T60, T43) can then tighten these thresholds as proof of progress, and any regression is caught automatically.

### T59: Wire `_should_deliver_early()` for Small Teams
- **Status**: open
- **Priority**: 1 (highest impact for Medium/Hard)
- **Difficulty**: Easy (1-2 hours)
- **Files**: `grocery_bot/planner/steps.py`
- **Root cause**: `_should_deliver_early()` in `delivery.py` is dead code. On 3-5 bot teams, bots with 1 active item walk to far items when delivering immediately would be cheaper. This inflates rounds-per-order.
- **How to fix**: In `_step_deliver_active`, before the `d_to_drop <= DELIVER_WHEN_CLOSE_DIST` check, add early delivery gated on `self.cfg.enable_early_delivery`:
  ```python
  if self.cfg.enable_early_delivery and self._should_deliver_early(ctx.pos, ctx.inv):
      self._emit_delivery_move_or_wait(...)
      return True
  ```
- **Gate**: `cfg.enable_early_delivery` is True for 4 ≤ num_bots < 8 (T33 showed it regresses Expert).
- **Expected gain**: +5-10 Medium, +5-10 Hard.
- **TDD**: Write test that verifies early delivery triggers for 3-bot team when cost comparison favors it. Tighten T61 rounds-per-order thresholds for 3-bot and 5-bot maps.

### T60: Lower Non-Active Clear Threshold for Medium Teams
- **Status**: open
- **Priority**: 1 (directly addresses Hard InvFull)
- **Difficulty**: Easy (1 hour)
- **Files**: `grocery_bot/team_config.py`, `grocery_bot/planner/steps.py`
- **Root cause**: `nonactive_clear_min_inv()` returns `MAX_INVENTORY (3)` for 4-7 bot teams. Bot 4 on Hard held 2 non-active items for 41 rounds waiting for a 3rd. The 3-item threshold is too conservative.
- **How to fix**: In `get_team_config()`, add a `nonactive_clear_threshold` flag and lower it to `MIN_INV_FOR_NONACTIVE_DELIVERY` (2) for medium teams:
  ```python
  # In team_config.py get_team_config():
  nonactive_clear_threshold = MIN_INV_FOR_NONACTIVE_DELIVERY if num_bots >= 4 else MAX_INVENTORY
  ```
- **Expected gain**: +5-10 Hard, +2-5 Medium.
- **TDD**: Write test for 5-bot team clearing at 2 items instead of 3. Tighten T61 InvFull threshold for 5-bot maps.

### T43: Fix `_spare_slots` Over-Conservatism
- **Status**: open
- **Priority**: 2
- **Difficulty**: Medium (2-3 hours)
- **Files**: `grocery_bot/planner/round_planner.py`
- **Root cause**: `_spare_slots(inv)` globally reserves slots for `active_on_shelves` across ALL bots. Unassigned bots can't preview-pick even when other bots handle all active items.
- **How to fix**: Per-bot assignment awareness:
  ```python
  def _spare_slots(self, inv: list[str], bid: int = -1) -> int:
      my_active = len(self.bot_assignments.get(bid, []))
      reserve = min(self.active_on_shelves, max(0, my_active))
      return (MAX_INVENTORY - len(inv)) - reserve
  ```
- **Expected gain**: +3-8 Medium/Hard (more preview pipelining).
- **TDD**: Write test showing unassigned bot gets spare slots when assigned bots cover active items.

### T54: Reduce Oscillation on Expert (632 -> <200)
- **Status**: open
- **Priority**: 2
- **Difficulty**: Medium (2-4 hours)
- **Files**: `grocery_bot/planner/idle.py`
- **Root cause**: Idle positioning score produces near-ties that flip between adjacent cells. `IDLE_STAY_IMPROVEMENT_THRESHOLD=0.5` is insufficient when proximity penalties are volatile.
- **How to fix**:
  1. Scale stay threshold by team size: `threshold = 0.5 + 0.1 * max(0, num_bots - 3)`
  2. Add previous-position penalty in `_score()` to prevent going back
  3. Filter moves that go to any of the last 3 history positions (extend `_would_oscillate`)
- **Expected gain**: +5-10 Expert.

### T34: Activate Tail Bots on Nightmare
- **Status**: open
- **Priority**: 2 (large potential but harder to execute)
- **Difficulty**: Hard (4-8 hours)
- **Files**: `grocery_bot/planner/assignment.py`, `grocery_bot/planner/idle.py`
- **Root cause**: Assignment gives `active_picker_count = ceil(active_on_shelves / 3)` pickers. With 6-item orders and 20 bots, 11-15 bots sit idle. B16-B19 never contribute.
- **How to fix**: Assign surplus bots as secondary pickers targeting different map regions. Even slow far-side pickups beat 0 contribution.
- **Expected gain**: +20-40 Nightmare.

### T39: Single-Item Delivery for Large Teams
- **Status**: open
- **Priority**: 3
- **Difficulty**: Easy (1 hour)
- **Files**: `grocery_bot/planner/steps.py`
- **Root cause**: `MIN_INV_FOR_NONACTIVE_DELIVERY=2` blocks 1-item deliveries on Expert. Idle bots hold 1 speculative item worth +1 but never deliver it.
- **How to fix**: Already partially done — `min_inv = 1` for assigned bots on 8+ teams. Extend to unassigned idle bots too.
- **Expected gain**: +3-5 Expert.

---

## Quality Tasks (lower priority)

### T44: Split movement.py (417 lines -> ≤300)
- **Status**: done — `_pre_predict` split into 3 methods; 386 lines
- **Files**: `grocery_bot/planner/movement.py`

### T45: Split round_planner.py (395 lines -> ≤300)
- **Status**: done — `InventoryMixin` and `BlacklistMixin` extracted; 318 lines
- **Files**: `grocery_bot/planner/round_planner.py`

### T46: Split bot.py (618 lines -> ≤300)
- **Status**: done — `game_log.py` extracted with logging helpers; 449 lines
- **Files**: `bot.py`, `grocery_bot/game_log.py`

### T48: Add Type Annotations
- **Status**: open
- **Priority**: 0 (quality)
- **Files**: `bot.py`, `grocery_bot/simulator/*.py`, `grocery_bot/planner/steps.py`

---

## Completed Tasks

### Phase 3 (2026-03-08)
| Task | Result |
|------|--------|
| T49: Spawn dispersal | Fan-out for 20-bot teams. Nightmare +14 replay. |
| T50: Fix oscillation | A-B-A detection + break step. Nightmare 46→124 live. |
| T51: Non-active throttle | `num_bots//5` → `num_bots//3`. InvFull 423→248. |
| T52: Fix dropoff zones | `drop_off` passed to `init_static`. Dropoff infra now functional. |
| T53: Speculative pickup | Idle bots pick speculatively. Nightmare 152→320 live. |
| T54-partial: Dropoff radius | Clear/penalty radius scaled by bots-per-zone. Expert +20 live. |
| T55: Preview-targeted speculation | Preview items prioritized in speculative pickup. +27 replay. |
| T56: Visualizer improvements | Difficulty filter, labels, log sorting. |
| T58: Rotate spec eligibility | Tried, regresses — nearby-bot efficiency lost. Blocked. |

### Phase 2
| Task | Result |
|------|--------|
| T12-T17, T21-T22 | Cooperative pathfinding, pipeline, idle positioning, route tables, path caching, coordination. |
| T24: Diagnostics framework | Action tracking, waste%, inv-full waits metrics. |
| T25: Inventory clog investigation | Root cause: single-dropoff congestion. Needs planner changes. |
| T29: Cross-cutting perf | BFS optimization, endgame 30→40, dist cache 256→512. |
| T30-pf: Dropoff queuing infra | Precomputed zones, approach/wait cells, congestion detection. |
| T31: Waste% investigation | Waste% misleading — preview pickup is optimal. No code change. |
| T32: Scale concurrent deliverers | `max(2, num_bots//4)` for 8+ bots. Expert +6.3. |
| T33: Wire dropoff queuing | Congestion avoidance + cascade detours. Expert +1.1. |
| T36-T37, T40, T42 | Investigated, all regress. No code changes. |
| T41: Production refactor | All files under 300 lines, 432 tests. |
| T47: Centralize constants | 12 constants moved to constants.py. |

### Phase 1
| Task | Result |
|------|--------|
| T1-T11 | Foundation: deadlock fix, Hungarian assignment, interleaved delivery, simulator, collision tests, refactor. |
| T19-T20, T23 | Code quality: SRP refactor, package structure, test coverage (230→327 tests). |

---

## Process Notes

- **TDD required**: Write tests BEFORE implementing fixes
- **Commit style**: Short single-sentence messages, no co-author line
- **Validate on live server**: Simulator scores alone are insufficient
- **Worktree warning**: Verify worktree code is merged before marking done (T50 incident)
- **Run regression**: `python -m pytest tests/test_replay_regression.py -q` after any merge
- **File size limit**: 300 lines max per file. See T44-T46 for violations.

## Replay Analyzer

```sh
python analyze_replay.py <log>           # Summary + problems
python analyze_replay.py <log> --grid 50 # ASCII grid at round 50
python analyze_replay.py <log> --bot 3   # Bot timeline
python analyze_replay.py <log> --rounds 40-60  # Round detail
```
