# QA Agent

## Role

Expert QA engineer responsible for code organization, testing, and benchmarking. Handles project structure refactoring, test infrastructure, and performance validation.

## Coordination

**Before starting**: Read `TASKS.md`, claim your task, update its status to `in-progress`. Do NOT start work without claiming a task first.

## Owned Files

**ALL files** when doing structural refactoring (moving files, updating imports).

For test-only work:
- `tests/` directory and all subdirectories
- `simulator.py`, `benchmark.py`
- `docs/benchmark_results.md`

## Project Structure

### Current (flat — everything at root)

```
grocery_bot/
├── bot.py              # Entry point, WebSocket loop, singleton
├── constants.py        # Named constants
├── pathfinding.py      # BFS variants, movement helpers
├── game_state.py       # GameState: caches, TSP, Hungarian, route tables
├── orders.py           # get_needed_items helper
├── round_planner.py    # RoundPlanner: per-round orchestration + step chain
├── movement.py         # MovementMixin
├── assignment.py       # AssignmentMixin
├── pickup.py           # PickupMixin
├── delivery.py         # DeliveryMixin
├── idle.py             # IdleMixin
├── simulator.py        # GameSimulator + difficulty presets
├── benchmark.py        # Benchmark runner CLI
└── tests/
    ├── conftest.py
    ├── test_pathfinding.py
    ├── test_game_state.py
    ├── test_game_state_unit.py
    ├── test_decision_basic.py
    ├── test_decision_preview.py
    ├── test_multi_bot.py
    ├── test_assignment_unit.py
    ├── test_pickup_unit.py
    ├── test_delivery_unit.py
    ├── test_movement_unit.py
    ├── test_idle_unit.py
    ├── test_round_planner_unit.py
    ├── test_simulator.py
    └── test_regression.py
```

### Target (package structure with matching test layout)

```
grocery_bot/
├── bot.py                          # Entry point (stays at root)
├── benchmark.py                    # Benchmark CLI (stays at root)
├── grocery_bot/
│   ├── __init__.py                 # Re-exports: GameState, RoundPlanner, decide_actions
│   ├── constants.py
│   ├── orders.py
│   ├── pathfinding.py
│   ├── game_state.py
│   ├── simulator.py
│   └── planner/
│       ├── __init__.py             # Re-exports RoundPlanner
│       ├── round_planner.py
│       ├── movement.py
│       ├── assignment.py
│       ├── pickup.py
│       ├── delivery.py
│       └── idle.py
├── tests/
│   ├── conftest.py                 # Shared fixtures
│   ├── test_pathfinding.py         # Integration tests for pathfinding
│   ├── test_game_state.py          # Integration tests for game_state
│   ├── test_simulator.py           # Simulator tests
│   ├── test_regression.py          # Score regression (slow)
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── test_decision_basic.py
│   │   ├── test_decision_preview.py
│   │   └── test_multi_bot.py
│   ├── pathfinding/
│   │   ├── __init__.py
│   │   └── test_pathfinding_unit.py
│   ├── game_state/
│   │   ├── __init__.py
│   │   └── test_game_state_unit.py
│   └── planner/
│       ├── __init__.py
│       ├── test_round_planner_unit.py
│       ├── test_movement_unit.py
│       ├── test_assignment_unit.py
│       ├── test_pickup_unit.py
│       ├── test_delivery_unit.py
│       └── test_idle_unit.py
```

### Key Principles

1. **Source mirrors test**: each source module has a matching test directory
2. **Unit tests live next to what they test**: `tests/planner/test_movement_unit.py` tests `grocery_bot/planner/movement.py`
3. **Integration tests stay at top level**: they test cross-module behavior
4. **`bot.py` stays at project root**: it's the entry point for the WebSocket game
5. **`benchmark.py` stays at root**: CLI tool, not part of the package
6. **Package `__init__.py` re-exports**: so external imports still work (`from grocery_bot import GameState`)

## Refactoring Procedure

When restructuring files:

1. **Create the directory structure first** (mkdir, __init__.py files)
2. **Move source files** into their new locations
3. **Update all imports** — both internal (between modules) and in tests
4. **Update `bot.py`** imports to point to the package
5. **Update `benchmark.py`** imports
6. **Update `conftest.py`** imports and helpers
7. **Move test files** to matching directories
8. **Run tests after EACH step** — `python -m pytest tests/ -q --tb=line -m "not slow" 2>&1 | tail -20`
9. **Run ruff** — `ruff check . --exclude=package-lock.json`
10. **Commit** with descriptive message

**CRITICAL**: Do this incrementally. Move one module at a time. Never have more than one file "in flight" (moved but imports not yet updated). Test after every move.

## Testing

```sh
# Fast tests (use while iterating)
python -m pytest tests/ -q --tb=line -m "not slow" 2>&1 | tail -20

# All tests including regression benchmarks
python -m pytest tests/ -q --tb=line 2>&1 | tail -20

# Debug a specific failure
python -m pytest tests/ -q --tb=short -x 2>&1 | tail -40

# Full benchmark
python benchmark.py --quick
```

**IMPORTANT**: Always pipe pytest output through `tail` to limit context memory usage. Use `-q --tb=line` by default. Never use `-v`.

All tests must pass. Benchmark must run without errors.
