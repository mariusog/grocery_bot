# Grocery Bot

## Project Structure

```
grocery_bot/                    # Main package
├── __init__.py                 # Re-exports: GameState, RoundPlanner
├── constants.py                # Named constants (tuning parameters)
├── orders.py                   # Order helpers (get_needed_items)
├── pathfinding.py              # BFS variants, direction helpers
├── game_state/                 # GameState package: caches, routing, assignment
│   ├── __init__.py             # Re-exports: GameState
│   ├── state.py                # GameState class: init, reset, static setup
│   ├── distance.py             # DistanceMixin: BFS distance + caching
│   ├── route_tables.py         # RouteTableMixin: precomputed pickup routes
│   ├── tsp.py                  # TspMixin: TSP solver, multi-trip planning
│   ├── hungarian.py            # AssignmentMixin: bot-to-item assignment
│   ├── dropoff.py              # DropoffMixin: congestion management
│   └── path_cache.py           # PathCacheMixin: per-bot path caching
├── simulator/                  # Simulator package
│   ├── __init__.py             # Re-exports: GameSimulator, presets, runner
│   ├── game_simulator.py       # GameSimulator: game loop, physics
│   ├── replay_simulator.py     # ReplaySimulator: recorded map replay
│   ├── map_generator.py        # Store layout and order generation
│   ├── diagnostics.py          # DiagnosticTracker: per-round metrics
│   ├── presets.py              # DIFFICULTY_PRESETS dict
│   ├── runner.py               # run_benchmark(), profile_congestion()
│   └── log_replay.py           # Log replay: verify live scores via physics
└── planner/                    # Per-round decision subpackage
    ├── __init__.py             # Re-exports: RoundPlanner
    ├── round_planner.py        # RoundPlanner: step-chain orchestration
    ├── steps.py                # StepsMixin: all _step_* decision methods
    ├── coordination.py         # CoordinationMixin: delivery queue, roles, tasks
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
├── game_state/                 # Matches grocery_bot/game_state/
│   ├── test_game_state.py
│   └── test_game_state_unit.py
└── planner/                    # Matches grocery_bot/planner/
    ├── test_round_planner_unit.py
    ├── test_movement_unit.py
    ├── test_assignment_unit.py
    ├── test_pickup_unit.py
    ├── test_delivery_unit.py
    ├── test_idle_unit.py
    ├── test_role_assignment.py
    ├── test_step_ordering.py
    ├── test_dropoff_steps.py
    ├── test_rush_endgame.py
    ├── test_plan_integrity.py
    ├── test_spare_slots.py
    └── test_nonactive_clearing.py
```

## Code Quality Standards

All code in this project MUST follow these principles. The QA agent enforces them strictly.

### Hard Limits
- **300 lines max per file** (source and test)
- **200 lines max per class**
- **30 lines max per method** (excluding docstrings)
- **No magic numbers** — all thresholds in `constants.py`
- **Type annotations required** on all function signatures

### SOLID Principles
- **SRP**: Every class/function has one responsibility. If you can say "and", split it.
- **OCP**: Step chain is extensible without modifying `_decide_bot()`.
- **LSP**: `ReplaySimulator` is a drop-in for `GameSimulator`.
- **ISP**: Specific imports only. No `import *`.
- **DIP**: Planners use `gs.dist_static()`, never `bfs_all()` directly.

### Law of Demeter
- Max one dot-chain: `self.gs.dist_static()` OK, `self.gs.dist_cache[pos].get(target)` NOT OK.

### Safety
- All BFS functions have `max_cells` bounds to prevent unbounded exploration
- Test data positions must be within grid bounds (`0 <= x < width`, `0 <= y < height`)
- No unbounded loops or recursion without explicit depth limits

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
| pathfinding-agent | `grocery_bot/pathfinding.py`, `grocery_bot/game_state/` (all files) | Routing, distance, collision, assignment |
| strategy-agent | `grocery_bot/planner/` (all files) | Per-round decisions, order management |
| qa-agent | `tests/`, `grocery_bot/simulator/` (all files), `benchmark.py`, `docs/` | Testing, benchmarking, profiling |

The lead-agent has cross-cutting authority — it may modify any file when a fix spans multiple agents' boundaries. Other agents treat `bot.py` and `grocery_bot/constants.py` as read-only.

## Running Tests

```sh
# Fast tests only (use this while iterating)
python -m pytest tests/ -q --tb=line -m "not slow" 2>&1 | tail -20

# Only on failure — rerun with details for the failing test
python -m pytest tests/ -q --tb=short -x 2>&1 | tail -40
```

**IMPORTANT for agents**: Use `-q --tb=line` by default. Never use `-v`. Only switch to `--tb=short` when debugging a specific failure.

## Running Benchmarks

Benchmarks write results to `docs/benchmark_results.md`. Read the report file instead of parsing stdout — this saves tokens.

```sh
# Default: replay maps (fast, single run per map)
python benchmark.py

# Synthetic multi-seed (use for statistical comparison)
python benchmark.py --synthetic --seeds 10 --diagnostics

# Quick single-seed for one difficulty
python benchmark.py --synthetic -d Nightmare --quick --diagnostics
```

**After running a benchmark**, read results from the generated files:
- `docs/benchmark_results.md` — scores and summary tables
- `logs/` — CSV+JSON log pairs for detailed analysis with `analyze_replay.py`

**Do NOT** pipe benchmark stdout through `tail` to extract scores. Instead, read the report:
```sh
python benchmark.py --synthetic --seeds 10
cat docs/benchmark_results.md
```

## Analyzing Game Runs

Use `analyze_replay.py` to debug bot behavior. Logs are generated when running benchmarks with `--diagnostics`.

```sh
# List available logs
python analyze_replay.py --list

# Summary + auto-detected problems (always run this first)
python analyze_replay.py <log>

# ASCII grid at round N (inspect positions, congestion)
python analyze_replay.py <log> --grid 50

# Bot timeline (condensed action streaks)
python analyze_replay.py <log> --bot 3

# Round-by-round detail (drill into problem areas)
python analyze_replay.py <log> --rounds 40-60

# Only problems (idle ≥10, oscillation ≥5, scoring gaps ≥20)
python analyze_replay.py <log> --problems
```

**After any optimization change**, agents MUST:
1. Run the benchmark with `--diagnostics` to generate a log
2. Read `docs/benchmark_results.md` for scores
3. Run `python analyze_replay.py <log>` to verify problem count and idle% improved
4. Use `--bot <id>` to check that previously-problematic bots improved
5. Include before/after scores and problem counts in the task result notes
