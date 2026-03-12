# Grocery Bot

## Project Tooling

| Tool | Command | Notes |
|------|---------|-------|
| **Test (fast)** | `python -m pytest tests/ -q --tb=line -m "not slow" 2>&1; echo "EXIT_CODE=$?"` | Check exit code (0=pass). |
| **Test (debug)** | `python -m pytest tests/path/file.py::test_name -q --tb=short 2>&1 \| tail -40` | Only for investigating a specific failure. |
| **Lint** | `ruff check <files>` | Auto-fix: `ruff check --fix <files>` |
| **Format** | `ruff format <files>` | Check only: `ruff format --check <files>` |
| **Type check** | `mypy <files>` | |
| **Security scan** | `bandit -r grocery_bot/ -ll` | Dependencies: `pip-audit` |
| **Log analysis** | `python analyze_replay.py <log> --problems 2>&1 \| tail -20` | See Analyzing Game Runs below. |
| **Benchmark** | `python benchmark.py --diagnostics` | Results go to `docs/benchmark_results.md`. |
| **Constants file** | `grocery_bot/constants.py` | All magic numbers and tuning parameters. |
| **Test fixtures** | `tests/conftest.py` | Shared factories and setup/teardown. |

## Game Rules

This bot competes in the NM i AI 2026 warm-up challenge. Understanding these rules is **mandatory** before writing any game logic.

### Overview

Control a swarm of workers in a procedurally generated grocery store via WebSocket. Bots navigate a grid, pick items from shelves, and deliver them to drop-off zones to fulfill sequential orders. **Goal: maximize score within the round limit.**

### Difficulty Levels

| Level | Grid | Bots | Aisles | Item Types | Order Size | Drop Zones | Rounds |
|-------|------|------|--------|------------|------------|------------|--------|
| Easy | 12x10 | 1 | 2 | 4 | 3-4 | 1 | 300 |
| Medium | 16x12 | 3 | 3 | 8 | 3-5 | 1 | 300 |
| Hard | 22x14 | 5 | 4 | 12 | 3-5 | 1 | 300 |
| Expert | 28x18 | 10 | 5 | 16 | 4-6 | 1 | 300 |
| Nightmare | 30x18 | 20 | 6 | 21 | 4-7 | 3 | 500 |

One map per difficulty. Item placement and orders change daily -- same day, same game (**deterministic**).

### Scoring

| Event | Points |
|-------|--------|
| Item delivered | +1 |
| Order completed | +5 bonus |

Leaderboard score = sum of best score on each of the 5 maps.

### Sequential Orders (CRITICAL)

- **Active order** -- the current order. You can deliver items for it.
- **Preview order** -- the next order. Visible but you **cannot deliver to it yet**. You can pre-pick items.
- **Infinite** -- when you complete an order, a new one appears. Orders never run out. Rounds are the only limit.
- Only 2 orders visible at a time (active + preview).

### Actions (one per bot per round)

| Action | Description |
|--------|-------------|
| `move_up/down/left/right` | Move one cell in that direction |
| `pick_up` (+ `item_id`) | Pick up item from adjacent shelf (Manhattan distance 1) |
| `drop_off` | Deliver matching items at drop-off zone |
| `wait` | Do nothing |

**Invalid actions are treated as `wait`** (no penalty, but wastes a round). **Do NOT validate moves or pickups client-side** -- the server handles them safely. Only `drop_off` can cause a penalty (see below).

### Penalty Definition (CRITICAL)

A **penalty** is defined as a **10-SECOND WAIT** imposed by the server. During the penalty, the game clock keeps ticking but you cannot act -- you lose ~2 rounds. This is catastrophic for scoring. The ONLY known penalty trigger is an illegal `drop_off` (see Dropoff Rules). Invalid moves, invalid pickups, and other bad actions are NOT penalized -- they are silently treated as `wait`.

### Pickup Rules

- Bot must be **adjacent** (Manhattan distance 1) to the shelf with the item
- Bot inventory must not be full (**max 3 items**)
- `item_id` must match an item on the map
- Invalid pickups are treated as `wait` -- **NO penalty**

### Dropoff Rules (CRITICAL -- most common source of bugs)

- Bot must be **standing on** the drop-off cell
- **Only items matching the active order are delivered** -- non-matching items stay in inventory
- **ILLEGAL MOVE: `drop_off` when NO inventory items match the active order causes a 10-SECOND PENALTY** -- always verify at least one carried item matches remaining active order needs before emitting `drop_off`
- `bot.py:_validate_actions()` is the safety net -- it ONLY checks `drop_off` legality. Do NOT add move/pickup validation there (it cripples multi-bot coordination and caused a 181 vs 337 score regression)
- When an order completes, the next order activates and remaining items are **re-checked against the new active order**
- Multiple drop-off zones (Nightmare has 3) are interchangeable

### Constraints

- **300 rounds** max per game (500 Nightmare), **120 seconds** wall-clock (300s Nightmare)
- **3 items** per bot inventory
- **Collision** -- bots block each other (no two on same tile, except spawn)
- **Move resolution is sequential by bot ID** (0, 1, 2, ...). Each bot's move is resolved against the current board state including earlier bots' already-applied moves. This means:
  - Higher-ID bots CAN follow lower-ID bots into vacated cells (chain moves)
  - Lower-ID bots CANNOT follow higher-ID bots (occupant hasn't moved yet)
  - Swap collisions (A→B, B→A) block both bots
  - Convergence on empty cell: lower-ID bot wins, higher-ID bot blocked
- **Full visibility** -- entire map visible every round
- **2-second timeout** per round for response
- Disconnect = game over (no reconnect)

### Coordinate System

- Origin (0, 0) is top-left
- X increases right, Y increases down

### Oracle Knowledge

Games are **deterministic per day** -- same map, same order sequence. Each game has 50 orders (500 on Nightmare) but only 2 are visible at a time (active + preview). **New orders are only revealed by completing orders** -- completing order N promotes the preview to active and reveals order N+2 as the new preview. So faster completion = more orders discovered per run.

We record every order seen during live play and save to `maps/` directory. Across multiple runs on the same day, we accumulate the full order sequence. On subsequent runs, `bot.py` loads matching recorded orders on round 0, giving the planner knowledge of future orders beyond the 2 visible ones. This creates an **improve loop**: play -> record orders -> optimize with knowledge -> play faster -> record MORE orders -> repeat.

## AI Agent Ground Rules

Read this section FIRST. These rules save you from wasting tokens and making common mistakes.

### NEVER Do These

- **NEVER use verbose test output** -- use quiet mode and pipe through `tail`
- **NEVER read raw CSV log files** -- read `docs/benchmark_results.md` first, use `analyze_replay.py` for drill-down
- **NEVER parse stdout to extract results** -- read the generated report files instead
- **NEVER use JSON lines for high-volume data** -- use CSV (4x more token-efficient)
- **NEVER dump full file contents when a summary exists** -- read summaries first, drill down on demand
- **NEVER use unseeded randomness** -- all randomized code MUST accept a `seed` parameter
- **NEVER modify files owned by another agent** -- add a task to `TASKS.md` instead

### ALWAYS Do These

- **ALWAYS pipe command output through `tail`** -- bound your token consumption
- **ALWAYS read TASKS.md before starting work** -- claim a task, set it to `in-progress`
- **ALWAYS run tests before committing** -- zero tolerance for test failures
- **ALWAYS include before/after metrics** when reporting optimization results
- **ALWAYS log the seed** in every run so results can be replicated

### Token Budget Awareness

You are an AI agent with a finite context window. Optimize for it:

| Action | Token-Efficient Way | Token-Wasteful Way |
|--------|--------------------|--------------------|
| Check test results | `python -m pytest tests/ -q --tb=line -m "not slow" 2>&1; echo "EXIT_CODE=$?"` | Verbose test output (unbounded) |
| Read benchmark results | `cat docs/benchmark_results.md` | Parse stdout from benchmark run |
| Inspect a log | `python analyze_replay.py <log> --problems` | Read the raw CSV file |
| Compare two runs | `python analyze_replay.py <log> --compare <other>` | Read both files and diff manually |
| Understand bot behavior | `python analyze_replay.py <log> --bot <id>` | Read 200 rows of per-round data |
| Check for problems | `python analyze_replay.py <log> --problems` | Read full summary + all data |

### Codebase Orientation (when starting)

When dropped into this codebase, read in this order:

1. **CLAUDE.md** -- this file (project rules, structure, conventions)
2. **TASKS.md** -- what work is in progress, what's done, what's open
3. **Project structure** -- `ls` the source and test directories
4. **`grocery_bot/constants.py`** -- all tuning parameters and configuration values
5. **`tests/conftest.py`** -- understand the shared setup and factory functions
6. **The specific files related to your task** -- only then dive into source code

Do NOT read every file. Read the minimum needed for your task.

### Skill Selection Guide

After writing or modifying code, use this decision tree:

```
Did you write new code?
+-- Yes: Run /test-coverage (verify tests exist for new public methods)
+-- Did tests fail?
|   +-- Yes: Run /debugging skill. Do NOT proceed until green.
+-- Is this a performance-sensitive change?
|   +-- Yes: Run /performance-optimization
+-- Ready to ship?
|   +-- Yes: Run /production-quality (orchestrates all quality skills)
+-- Quick quality check only?
    +-- Yes: Run /lint + /code-review
```

For new features, use `/tdd-cycle` (write tests first, then implement).

## Project Structure

```
grocery_bot/                    # Main package
├── __init__.py                 # Re-exports: GameState, RoundPlanner
├── constants.py                # Named constants (tuning parameters)
├── team_config.py              # TeamConfig dataclass + get_team_config()
├── orders.py                   # Order helpers (get_needed_items)
├── pathfinding.py              # BFS variants, direction helpers
├── game_log.py                 # Game loop logging and map recording helpers
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
    ├── _base.py                # PlannerBase: shared attribute stubs for mypy
    ├── round_planner.py        # RoundPlanner: step-chain orchestration
    ├── steps.py                # StepsMixin: all _step_* decision methods
    ├── coordination.py         # CoordinationMixin: delivery queue, roles, tasks
    ├── movement.py             # MovementMixin: BFS dispatch, collision, emit
    ├── assignment.py           # AssignmentMixin: bot-to-item assignment
    ├── pickup.py               # PickupMixin: active/preview pickup, TSP routes
    ├── delivery.py             # DeliveryMixin: delivery timing, end-game
    ├── idle.py                 # IdleMixin: dropoff clearing, idle positioning
    ├── preview.py              # PreviewMixin: preview-order pickup routing
    ├── speculative.py          # SpeculativeMixin: idle-bot speculative pickup
    ├── spawn.py                # SpawnMixin: opening-round dispersal
    ├── inventory.py            # InventoryMixin: inventory counting and allocation
    └── blacklist.py            # BlacklistMixin: pickup failure detection and expiry

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
    ├── conftest.py             # Planner-specific fixtures
    ├── test_round_planner_lifecycle.py
    ├── test_round_planner_helpers.py
    ├── test_movement_core.py
    ├── test_movement_advanced.py
    ├── test_movement_predict.py
    ├── test_corridor_yield.py
    ├── test_assignment_core.py
    ├── test_assignment_unit.py
    ├── test_assignment_advanced.py
    ├── test_pickup_core.py
    ├── test_pickup_routing.py
    ├── test_delivery_unit.py
    ├── test_idle_unit.py
    ├── test_idle_dropoff.py
    ├── test_role_assignment.py
    ├── test_coordination_unit.py
    ├── test_preview_guard.py
    ├── test_preview_walkers.py
    ├── test_speculative_unit.py
    ├── test_smart_speculative.py
    ├── test_spawn_dispersal.py
    ├── test_step_ordering.py
    ├── test_dropoff_steps.py
    ├── test_rush_endgame.py
    ├── test_plan_integrity.py
    ├── test_spare_slots.py
    ├── test_nonactive_clearing.py
    ├── test_active_priority.py
    ├── test_active_saturation.py
    ├── test_duplicate_active.py
    └── test_phase1_boosts.py
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
- Run `python -m pytest tests/ -q --tb=line -m "not slow" 2>&1; echo "EXIT_CODE=$?"` before committing — exit code must be 0

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

## Testing Standards

### Coverage Requirements

**Every public method and function MUST have at least one dedicated test.** Non-negotiable.

Test naming: `test_<method_name>_<scenario>` -- e.g., `test_calculate_score_empty_input_returns_zero`

### Unit Test Checklist (per method)

1. **Happy path** -- normal input, expected output
2. **Edge cases** -- empty inputs, zero values, boundary conditions
3. **Error conditions** -- invalid input, unreachable targets, overflow
4. **State mutations** -- verify side effects

### Test Quality Rules

- **Arrange-Act-Assert** pattern in every test
- **One assertion per concept** -- test one behavior, not five
- **No test interdependence** -- each test creates its own state via fixtures/factories
- **Deterministic** -- no random inputs without fixed seeds
- **Descriptive names** -- `test_search_stops_at_max_depth` not `test_search_1`

### When Tests Fail

1. Read the failure output (the `tail` you already have)
2. If the error is clear, fix it and rerun
3. If unclear, rerun the single failing test with more detail (see Test debug command)
4. If the failure is in another agent's code, do NOT fix it -- add a task to TASKS.md
5. If a test is flaky (passes sometimes, fails sometimes), it has a non-determinism bug -- fix the seed

## Running Tests

```sh
# Fast tests only (use this while iterating)
# IMPORTANT: always check exit code, not just tail output — summary line can be cut off
python -m pytest tests/ -q --tb=line -m "not slow" 2>&1; echo "EXIT_CODE=$?"

# Only on failure — rerun with details for the failing test
python -m pytest tests/path/file.py::test_name -q --tb=short 2>&1 | tail -40

# If tests appear stuck, install pytest-timeout and use:
# pip install pytest-timeout
# python -m pytest tests/ -q --tb=short -m "not slow" --timeout=10 --timeout_method=thread --ignore=tests/test_replay_regression.py 2>&1; echo "EXIT_CODE=$?"
```

**IMPORTANT for agents**:
- Use `-q --tb=line` by default. Never use `-v`. Only switch to `--tb=short` when debugging a specific failure.
- **Always append `; echo "EXIT_CODE=$?"` instead of piping through `tail`** — with `-q` mode the summary line ("N passed") can be cut off by `tail`, making it impossible to confirm pass/fail. Exit code 0 = all passed.
- **If a test hangs**, install `pytest-timeout` (`pip install pytest-timeout`) and rerun with `--timeout=10 --timeout_method=thread` to get a stack trace showing where the code is stuck. Then fix the root cause — do not work around it with `--ignore`.
- **Fix broken/hanging tests even if pre-existing** — do not skip or ignore known failures. If you encounter a broken test, fix the root cause (or file a task in TASKS.md if it's outside your ownership).
- **Replay regression tests** (`tests/test_replay_regression.py`): by default only the latest day's maps run (fast, ~5s). Full history is `@pytest.mark.slow` — run with `-m slow` when needed.

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

## Git Conventions

### Commit Messages

- Short, single-sentence, present tense: `Fix cache invalidation on round reset`
- Focus on WHY, not WHAT: `Prevent stale distances after entity moves` not `Change line 42 in distance.py`
- One logical change per commit

### Staging

- **Stage specific files by name** -- never use `git add .` or `git add -A` (risks committing secrets, logs, cache files)
- Check `git status` before committing -- verify only intended files are staged
- Never commit files matching `.gitignore` patterns

### Branches

- `main` is the stable branch -- all tests pass, benchmarks meet baselines
- Feature branches: `<agent>/<task-id>-<short-description>` e.g. `pathfinding/T12-cache-invalidation`
- Never force-push to `main`
