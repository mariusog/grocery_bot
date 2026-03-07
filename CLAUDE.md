# Grocery Bot

## Project Structure

```
grocery_bot/                    # Main package
├── __init__.py                 # Re-exports: GameState, RoundPlanner
├── constants.py                # Named constants (tuning parameters)
├── orders.py                   # Order helpers (get_needed_items)
├── pathfinding.py              # BFS variants, direction helpers
├── game_state.py               # GameState: caches, TSP, Hungarian, route tables
├── simulator.py                # GameSimulator + DIFFICULTY_PRESETS
└── planner/                    # Per-round decision subpackage
    ├── __init__.py             # Re-exports: RoundPlanner
    ├── round_planner.py        # RoundPlanner: step-chain orchestration
    ├── movement.py             # MovementMixin: BFS dispatch, collision, emit
    ├── assignment.py           # AssignmentMixin: bot-to-item assignment
    ├── pickup.py               # PickupMixin: active/preview pickup, TSP routes
    ├── delivery.py             # DeliveryMixin: delivery timing, end-game
    └── idle.py                 # IdleMixin: dropoff clearing, idle positioning

bot.py                          # Entry point: WebSocket loop, decide_actions()
benchmark.py                    # CLI benchmark runner

tests/
├── conftest.py                 # Shared fixtures: make_planner, make_state, etc.
├── test_simulator.py           # Simulator edge cases and presets
├── test_regression.py          # Score regression (slow, 20-seed)
├── integration/                # Cross-module integration tests
│   ├── test_decision_basic.py
│   ├── test_decision_preview.py
│   └── test_multi_bot.py
├── pathfinding/                # Matches grocery_bot/pathfinding.py
│   └── test_pathfinding.py
├── game_state/                 # Matches grocery_bot/game_state.py
│   ├── test_game_state.py
│   └── test_game_state_unit.py
└── planner/                    # Matches grocery_bot/planner/
    ├── test_round_planner_unit.py
    ├── test_movement_unit.py
    ├── test_assignment_unit.py
    ├── test_pickup_unit.py
    ├── test_delivery_unit.py
    └── test_idle_unit.py
```

## Multi-Agent Coordination Protocol

When multiple agents run in parallel (via worktrees), they MUST follow this protocol.

### Before Starting Work

1. Read `TASKS.md` to see available tasks and what is already claimed
2. Pick a task that matches your role (see agent file in `.claude/agents/`)
3. Update `TASKS.md`: set the task status to `in-progress` and add your agent name
4. Only then begin implementation

### While Working

- **Stay in your lane**: only modify files listed in your agent's "Owned Files" table
- **One task at a time**: finish or abandon a task before claiming another
- If you discover work needed in another agent's files, add a new task to `TASKS.md` assigned to that agent — do NOT modify their files
- Run `python -m pytest tests/ -q --tb=line -m "not slow" 2>&1 | tail -20` before committing — all tests must pass

### When Done

1. Update `TASKS.md`: set the task status to `done` and add a brief result note
2. Commit your changes with a descriptive message
3. If your change needs validation by QA, add a `needs-benchmark` task to TASKS.md

### Conflict Prevention

- Never claim a task already marked `in-progress`
- If two tasks seem related, check if the other agent is already covering it
- Pathfinding Agent and Strategy Agent must not both change routing logic simultaneously — coordinate via TASKS.md
- QA Agent benchmarks AFTER other agents commit, not in parallel with active changes

## File Ownership

| Agent | Owned Files | Role |
|-------|-------------|------|
| lead-agent | `bot.py`, `grocery_bot/constants.py`, `TASKS.md`, `CLAUDE.md`, `.claude/agents/` | Architecture, cross-cutting changes, task design |
| pathfinding-agent | `grocery_bot/pathfinding.py`, `grocery_bot/game_state.py` | Routing, distance, collision, assignment |
| strategy-agent | `grocery_bot/planner/` (all files) | Per-round decisions, order management |
| qa-agent | `tests/`, `grocery_bot/simulator.py`, `benchmark.py`, `docs/` | Testing, benchmarking, profiling |

The lead-agent has cross-cutting authority — it may modify any file when a fix spans multiple agents' boundaries. Other agents treat `bot.py` and `grocery_bot/constants.py` as read-only.

## Running Tests

```sh
# Fast tests only (use this while iterating)
python -m pytest tests/ -q --tb=line -m "not slow" 2>&1 | tail -20

# All tests including regression benchmarks
python -m pytest tests/ -q --tb=line 2>&1 | tail -20

# Only on failure — rerun with details for the failing test
python -m pytest tests/ -q --tb=short -x 2>&1 | tail -40

# Full benchmark across difficulties
python benchmark.py

# Quick single-seed benchmark
python benchmark.py --quick
```

**IMPORTANT for agents**: Always pipe pytest output through `tail` to avoid flooding your context with hundreds of lines. Use `-q --tb=line` by default, only switch to `--tb=short` when debugging a specific failure. Never use `-v` — it generates excessive output that wastes context memory.
