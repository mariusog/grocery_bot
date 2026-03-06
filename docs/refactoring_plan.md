# Refactoring Plan: Grocery Bot Codebase

## Section 1: Current State

### File inventory and line counts

| File | Lines | Role |
|------|------:|------|
| `bot.py` | 261 | Thin orchestrator, WebSocket loop, module-level singleton + backward-compat wrappers |
| `pathfinding.py` | 390 | BFS variants (standard, corridor-weighted, temporal), direction helpers, `get_needed_items` |
| `game_state.py` | 477 | GameState class: caches, TSP, Hungarian algorithm, idle spot + corridor computation |
| `round_planner.py` | 397 | RoundPlanner: per-round orchestration + 5 mixin imports |
| `movement.py` | 158 | MovementMixin: BFS dispatch, collision, emit helpers |
| `assignment.py` | 228 | AssignmentMixin: bot-to-item assignment, preview bot, urgency |
| `pickup.py` | 327 | PickupMixin: active pickup, greedy/assigned routes, flexible TSP |
| `delivery.py` | 111 | DeliveryMixin: end-game estimation, early delivery |
| `idle.py` | 118 | IdleMixin: dropoff clearing, idle positioning |
| `simulator.py` | 642 | GameSimulator + `run_benchmark` + `profile_congestion` |
| `benchmark.py` | 352 | Separate benchmark runner with timing wrappers |
| `test_bot.py` | 3530 | **137 tests** in 43 test classes, one file |
| **Total** | **6991** | |

### Key observations

- Every `.py` file lives at the project root -- no package structure.
- `test_bot.py` is a single 3530-line file containing all 137 tests plus 3 helper functions (`make_state`, `reset_bot`, `get_action`).
- `bot.py` maintains module-level mutable globals (`_blocked_static`, `_dist_cache`, etc.) alongside `GameState` singleton, with `_sync_globals_from_gs` / `_sync_gs_from_globals` functions to keep them in sync -- a pattern created for backward compatibility with early tests.
- Two separate benchmarking systems exist: `simulator.run_benchmark()` and `benchmark.run_benchmark()`, with duplicated difficulty presets (`DIFFICULTY_PRESETS` in `simulator.py`, `CONFIGS` in `benchmark.py`).
- No type hints on any function signature in production code. Only a few appear in docstrings.
- No `conftest.py` or shared fixtures -- `reset_bot()` is called 88 times manually.

---

## Section 2: Code Quality Issues

### P0 -- High impact, high risk of bugs

1. **Module-level mutable globals with manual sync** (`bot.py:37-63`)
   - `_blocked_static`, `_dist_cache`, `_adj_cache`, `_last_pickup`, `_pickup_fail_count`, `_blacklisted_items` are module globals.
   - `_sync_globals_from_gs()` and `_sync_gs_from_globals()` manually mirror them to/from the `GameState` singleton.
   - Any new state field requires updating both sync functions -- error-prone and easy to forget.
   - Tests directly mutate `bot._blacklisted_items` (test_bot.py:2909) and `bot._adj_cache` (test_bot.py:1655), coupling tests to internal implementation.

2. **`_full_state` monkey-patched onto RoundPlanner** (`bot.py:109`)
   - `planner._full_state = state` assigns an attribute that is not declared in `__init__`.
   - Used in `assignment.py:106` (`self._full_state["grid"]["width"]`) and `round_planner.py:105` (`self._full_state["grid"]`).
   - No type safety, no discoverability, breaks IDE autocomplete.

3. **Magic numbers throughout decision logic** (`round_planner.py`, `movement.py`, `idle.py`, `assignment.py`, `pickup.py`)
   - `self.endgame = self.rounds_left <= 30` (round_planner.py:29)
   - `max_dist = 6 if len(self.bots) >= 5 else float("inf")` (movement.py:150)
   - `d_to_drop <= 3` (round_planner.py:290)
   - `len(self.bots) <= 3` (round_planner.py:306)
   - `len(self.bots) >= 6` (round_planner.py:317)
   - `len(self.bots) >= 5 and self._nonactive_delivering >= 1` (round_planner.py:335)
   - `if drop_dist <= 3: s += (4 - drop_dist) * 3` (idle.py:85-86)
   - `if ob_dist <= 2: s += (3 - ob_dist) * 2` (idle.py:90-91)
   - `s += target_dist * 0.5` (idle.py:95)
   - `(stay_score - best_score) >= 0.5` (idle.py:112)
   - `d += abs(bot_zone - item_zone) * 3` (assignment.py:131, game_state.py:281)
   - `max_detour=3` (pickup.py:292)
   - `effective_max = (6 if best_cascade else max_detour)` (pickup.py:313)
   - `d + 0.3 * cluster_d` (pickup.py:238)
   - `gs.pickup_fail_count[last_item_id] >= 3` (round_planner.py:122)
   - `n_bots * n_items <= 100` threshold for Hungarian vs greedy (game_state.py:288, 328)
   - `self.order_nearly_complete = 0 < self.active_on_shelves <= 2` (round_planner.py:166)

   These should be named constants in a config module.

### P1 -- Moderate impact

4. **No type hints anywhere in production code**
   - Zero `-> ReturnType` annotations. Zero parameter type annotations.
   - Function signatures like `def _try_active_pickup(self, bid, bx, by, pos, inv, blocked)` give no indication of types.
   - Makes refactoring dangerous and IDE support minimal.

5. **God method: `_decide_bot`** (`round_planner.py:187-348`, 161 lines)
   - Contains the entire per-bot decision tree across 8 steps.
   - Deeply nested if/elif chains with complex conditions.
   - Should be broken into step-specific methods or use a chain-of-responsibility pattern.

6. **Duplicated benchmark infrastructure**
   - `simulator.py:522-568` (`run_benchmark`) and `benchmark.py:143-255` (`run_benchmark`) are two separate benchmark runners.
   - `simulator.py` has `DIFFICULTY_PRESETS`, `benchmark.py` has `CONFIGS` -- with **different values** for Medium and Hard (`num_item_types` and `items_per_order` differ).
   - `benchmark.py:84-135` (`run_single`) manually resets `bot._blocked_static` etc. instead of using `bot.reset_state()`.

7. **`get_needed_items` lives in `pathfinding.py`** (pathfinding.py:218-224)
   - This is an order-processing utility, not a pathfinding function.
   - Imported by `round_planner.py` from `pathfinding` -- conceptually wrong location.

8. **`corridor_cells` shared via module-level global in pathfinding.py** (`game_state.py:59`, `pathfinding.py:10`)
   - `GameState.init_static` sets `_pf._corridor_cells = self.corridor_cells` by importing `pathfinding` as `_pf` and mutating its module global.
   - This hidden coupling means `pathfinding.py` functions silently change behavior depending on whether `GameState.init_static` has been called.
   - Should be passed explicitly or accessed through a shared config object.

9. **Inconsistent blocking check in simulator** (`simulator.py:278-279`)
   - `if [x, y] in self.walls` uses list comparison against a list of tuples (walls are stored as tuples from `_generate_map` but compared as lists).
   - Works because of Python's value equality, but mixing list/tuple representations is confusing.

10. **`GameState.reset` calls `__init__`** (`game_state.py:24-25`)
    - `def reset(self): self.__init__()` is an anti-pattern. If `__init__` is ever extended with required parameters, this breaks silently.

### P2 -- Low impact / style

11. **`bot.py` re-exports internal names** (bot.py:17-27)
    - `from pathfinding import ... _predict_pos` -- re-exporting a private function.
    - Tests use `bot._predict_pos` directly. These should be public if they're part of the test API.

12. **Unused variable in `assign_items_to_bots`** (`game_state.py:263-267`)
    - `item_targets` list is built but never used. The loop's only purpose is computing adjacency, but the result is discarded.

13. **Unused variables** (`game_state.py:270-271`)
    - `bot_positions` and `item_positions` are computed but never used in `assign_items_to_bots`.

14. **Inconsistent docstring style**
    - Some functions have full Google-style docstrings with Args/Returns (pathfinding.py).
    - Others have one-line summaries only (most mixin methods).
    - Some have no docstrings at all (most methods in `round_planner.py`).

15. **Indentation error** (`round_planner.py:331`)
    - `if pos == self.drop_off:` is indented 8 spaces under an `if` that is indented 8 spaces -- the inner block looks like it's at the wrong level. Functionally correct but misleading.

---

## Section 3: Proposed Project Structure

```
grocery_bot/
    __init__.py              # Re-exports: GameState, RoundPlanner, decide_actions
    constants.py             # Named constants: ENDGAME_THRESHOLD, MAX_INVENTORY, etc.
    pathfinding.py           # BFS variants, direction_to, _predict_pos
    game_state.py            # GameState class (caches, TSP, Hungarian)
    orders.py                # get_needed_items (extracted from pathfinding.py)
    planner/
        __init__.py          # RoundPlanner class definition + plan()
        movement.py          # MovementMixin
        assignment.py        # AssignmentMixin
        pickup.py            # PickupMixin
        delivery.py          # DeliveryMixin
        idle.py              # IdleMixin
    simulator/
        __init__.py          # GameSimulator, DIFFICULTY_PRESETS
        benchmark.py         # Unified benchmark runner (merge current two)
        profiler.py          # profile_congestion, timing infrastructure
    bot.py                   # Entry point: decide_actions, play(), WebSocket loop

tests/
    conftest.py              # Shared fixtures: make_state, reset_bot, get_action,
                             #   common state builders, autouse reset fixture
    test_pathfinding.py      # BFS, direction_to, _predict_pos, find_adjacent
    test_game_state.py       # GameState: dist_static, TSP, Hungarian, idle spots
    test_orders.py           # get_needed_items
    test_decision_basic.py   # Single-bot decision logic (pickup, delivery, endgame)
    test_decision_preview.py # Preview pickup, cascade, pipelining
    test_multi_bot.py        # Multi-bot: assignment, collision, deadlock, yield
    test_simulator.py        # GameSimulator edge cases, difficulty presets
    test_benchmark.py        # Benchmark runner, profiling, diagnostic mode
    test_regression.py       # Score regression thresholds (TestScoreRegression,
                             #   TestCongestionRegression)
```

### Rationale

- **`grocery_bot/` package**: All production code under one importable package. `bot.py` stays at root as the entry point (or moves inside with a thin `__main__.py`).
- **`planner/` subpackage**: Groups the 5 mixins + orchestrator together. They're tightly coupled and always imported together.
- **`simulator/` subpackage**: Consolidates `simulator.py` + `benchmark.py` into one place. Eliminates the duplicate preset problem.
- **`constants.py`**: Single source of truth for all magic numbers.
- **`orders.py`**: `get_needed_items` belongs with order logic, not pathfinding.
- **`tests/`**: Separate directory with `conftest.py` for shared fixtures. Tests split by functional area.

---

## Section 4: Test Reorganization Plan

### Current state

- **137 tests** in **43 classes** in one **3530-line file**.
- 3 helper functions at the top: `make_state()`, `reset_bot()`, `get_action()`.
- `reset_bot()` is called manually at the start of nearly every test (88 occurrences).
- `make_state()` is called 77 times with verbose inline state dictionaries.
- Tests are roughly ordered by feature but not formally grouped.

### Proposed split

| New file | Test classes to move | Approx tests | Rationale |
|----------|---------------------|----------:|-----------|
| `conftest.py` | (fixtures only) | 0 | `make_state`, `reset_bot`, `get_action`, autouse `reset_bot` fixture, common state builders |
| `test_pathfinding.py` | `TestHelperFunctions`, `TestGetDistancesFrom` | 10 | Pure function tests |
| `test_game_state.py` | `TestMultiTripPlanning` (partial) | 3 | TSP, distance cache tests |
| `test_decision_basic.py` | `TestNoSingleItemDelivery`, `TestRushDeliveryWhenOrderCompletable`, `TestDontPickUpUnneededItems`, `TestEndGameSkipsDistantItems`, `TestSingleItemDeliveryWaste`, `TestNoRushWithSingleItem`, `TestDropoffAtDropoff`, `TestEndGamePartialDelivery`, `TestNoActiveOrder`, `TestSmarterDropoffTiming`, `TestImprovedEndGame`, `TestBotStuckInCorner`, `TestEmptyOrdersAndBlacklist` | 25 | Core single-bot decision logic |
| `test_decision_preview.py` | `TestPreviewPickupOnSecondTrip`, `TestOrderCompletionPriority`, `TestDeliveryCascade`, `TestItemProximityClustering`, `TestItemProximityClusteringAdvanced`, `TestPreviewDoesntBlockActive`, `TestStep5PreviewDetour`, `TestStep5PreviewDetourDeep`, `TestStep6DistantPreviewPrepick`, `TestStep6AdjacentPreviewPickup`, `TestDedicatedPreviewBot`, `TestPreviewPipeliningNearlyComplete` | 30 | Preview/cascade/pipelining |
| `test_multi_bot.py` | `TestMultiBotAssignment`, `TestAntiCollision`, `TestInterleavedDelivery`, `TestAntiDeadlock`, `TestMultiBotCollisionScenarios`, `TestMultiBotCollisionEdgeCases`, `TestSpawnDispersal` | 22 | Multi-bot coordination |
| `test_simulator.py` | `TestSimulatorEdgeCases`, `TestSimulatedGame`, `TestSimulatorDifficultyPresets`, `TestSimulatorPerformanceProfiling`, `TestOrderCascadeDelivery`, `TestPickupFailureRecovery`, `TestDiagnosticMode`, `TestCongestionProfiler` | 27 | Simulator internals |
| `test_regression.py` | `TestScoreRegression`, `TestCongestionRegression`, `TestSimulatorImprovements` | 20 | Slow regression tests (mark with `@pytest.mark.slow`) |

### Shared fixtures for `conftest.py`

```python
import pytest
import bot

@pytest.fixture(autouse=True)
def _reset_bot():
    """Auto-reset bot state before every test."""
    bot.reset_state()

def make_state(...):
    """Build a minimal game state dict for testing."""
    ...  # (current implementation)

def get_action(actions, bot_id=0):
    ...  # (current implementation)

# State builder shortcuts
@pytest.fixture
def easy_state():
    """Pre-built Easy game state with 1 bot."""
    return make_state(
        bots=[{"id": 0, "position": [5, 5], "inventory": []}],
        items=[...],
        orders=[...],
    )

@pytest.fixture
def two_bot_state():
    """Pre-built state with 2 bots for collision tests."""
    ...
```

### Key improvements

1. **Autouse `reset_bot` fixture** eliminates 88 manual `reset_bot()` calls.
2. **State builder fixtures** reduce verbose inline dict construction.
3. **`@pytest.mark.slow`** on regression tests (they run 20 seeds each) allows `pytest -m "not slow"` for fast iteration.
4. **Separate test files** enable running just `pytest tests/test_pathfinding.py` for focused work.

---

## Section 5: Architecture Recommendations

### 5.1 Mixin architecture assessment

The current mixin hierarchy:
```
RoundPlanner(MovementMixin, AssignmentMixin, PickupMixin, DeliveryMixin, IdleMixin)
```

**Problems with the current mixin approach:**

1. **Implicit `self` coupling**: Every mixin reads and writes attributes defined in `RoundPlanner.__init__` or other mixins. For example, `PickupMixin._try_active_pickup` reads `self.net_active`, `self.items_at_pos`, `self.claimed`, `self.bot_assignments` -- all defined in `RoundPlanner` or `AssignmentMixin`. There is no explicit interface between them.

2. **Cross-mixin method calls**: `PickupMixin` calls `self._emit_move` (from `MovementMixin`) and `self._claim` (from `RoundPlanner`). `AssignmentMixin` calls `self._is_delivering` and `self._iter_needed_items` (from `RoundPlanner`). The dependency graph is circular.

3. **No mixin can be tested in isolation**: You cannot instantiate `PickupMixin` without all of `RoundPlanner`'s state. This defeats the purpose of separation.

4. **Mixin boundaries are file-level only**: The code is split across files for readability, but all five mixins share one flat namespace on `self`. Any method name collision would be silent.

**Recommendation: Keep mixins, but harden boundaries.**

Composition (injecting separate collaborator objects) would be cleaner architecturally but would require passing 15+ shared attributes between objects, adding boilerplate without clear benefit for this codebase size. The pragmatic path:

- **Extract shared state into a dataclass** (`RoundContext`) that is passed explicitly to mixin methods, replacing implicit `self` attribute access.
- **Define a clear interface** for what each mixin expects (type-hinted `RoundContext`).
- **Rename mixins as step handlers** to clarify they are phases of `_decide_bot`, not independent behaviors.

### 5.2 Eliminate module-level globals in `bot.py`

The `_sync_globals_from_gs` / `_sync_gs_from_globals` pattern exists solely because early tests accessed `bot._blocked_static` etc. directly.

**Recommendation:**
- Delete all module-level globals and sync functions.
- Tests should use `bot._gs.blocked_static` (or better, dedicated test accessors).
- This eliminates 30 lines of error-prone sync code.

### 5.3 Pass `state` to RoundPlanner constructor properly

Replace the monkey-patched `planner._full_state = state` with:
- Adding `state` as a parameter to `RoundPlanner.__init__`.
- Extracting `grid_width` in the constructor rather than accessing `self._full_state["grid"]["width"]` deep in assignment code.

### 5.4 Unify benchmark infrastructure

Merge `benchmark.py` into `simulator.py` (or into a `simulator/benchmark.py` submodule). Key actions:
- Delete the duplicate `CONFIGS` dict in `benchmark.py`. Use `DIFFICULTY_PRESETS` from `simulator.py` everywhere.
- Use `bot.reset_state()` in `run_single` instead of manually resetting globals.
- Merge `timing_report()` into the simulator's existing profiling support.

### 5.5 Break up `_decide_bot`

The 161-line `_decide_bot` method has 8 numbered steps. Refactor into:

```python
def _decide_bot(self, bot):
    ctx = self._build_bot_context(bot)
    for step in self._steps:
        if step(ctx):
            return
    self._emit_wait(ctx)
```

Where `self._steps` is an ordered list of step methods, each returning `True` if it handled the bot. This makes the control flow explicit and each step independently testable.

---

## Section 6: Implementation Order

Ordered by risk (low to high) and impact (high to low).

### Phase 1: Zero-risk cleanup (no behavior change)

1. **Extract named constants** from magic numbers into `constants.py`.
   - Files: new `constants.py`, then update `round_planner.py`, `movement.py`, `idle.py`, `assignment.py`, `pickup.py`, `delivery.py`.
   - Risk: None (values unchanged, just named).
   - Impact: Readability, maintainability.

2. **Add type hints** to all function signatures.
   - Files: all `.py` files.
   - Risk: None (runtime behavior unchanged).
   - Impact: IDE support, catches type errors early.

3. **Move `get_needed_items`** from `pathfinding.py` to new `orders.py`.
   - Update imports in `round_planner.py`, `bot.py`.
   - Risk: Low (import path change only).

4. **Make `corridor_cells` dependency explicit** (`game_state.py:59`, `pathfinding.py:10`).
   - Pass `corridor_cells` as a parameter to BFS functions instead of mutating a module global.

5. **Remove unused variables** in `game_state.py:263-271`.

### Phase 2: Test infrastructure (enables safer future refactoring)

6. **Create `tests/conftest.py`** with `make_state`, `get_action`, autouse `reset_bot` fixture.
   - Split `test_bot.py` into the 7 proposed test files.
   - Remove 88 manual `reset_bot()` calls.
   - Add `@pytest.mark.slow` to regression tests.
   - Risk: Low (test-only changes).
   - Impact: 10x faster dev iteration with `pytest -m "not slow"`.

### Phase 3: Structural improvements

7. **Eliminate module-level globals** in `bot.py`.
   - Replace `bot._blocked_static` test accesses with `bot._gs.blocked_static`.
   - Delete `_sync_globals_from_gs`, `_sync_gs_from_globals`, and all 6 module globals.
   - Risk: Medium (tests need updating).
   - Impact: Eliminates a major bug vector.

8. **Pass `state` properly to RoundPlanner**.
   - Add `full_state` parameter to `__init__`, remove monkey-patch.
   - Risk: Low.

9. **Unify benchmark infrastructure**.
   - Merge `benchmark.py` into simulator or shared module.
   - Delete `CONFIGS` duplicate.
   - Risk: Low (tooling-only).

### Phase 4: Architecture (higher risk, do last)

10. **Create package structure** (`grocery_bot/`, `tests/`).
    - Move files, update all imports.
    - Risk: Medium (many import changes).
    - Impact: Professional project structure.

11. **Refactor `_decide_bot`** into step-chain pattern.
    - Risk: Medium (behavioral logic touched).
    - Must have regression tests passing first (Phase 2).

12. **Extract `RoundContext` dataclass** for mixin communication.
    - Risk: Medium-high (touches all mixin files).
    - Do after Phase 2 provides test safety net.
