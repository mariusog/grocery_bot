# Grocery Bot

## Multi-Agent Coordination Protocol

When multiple agents run in parallel (via worktrees), they MUST follow this protocol to avoid duplicating or conflicting work.

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
| pathfinding-agent | `pathfinding.py`, `game_state.py` | Routing, distance, collision, assignment |
| strategy-agent | `round_planner.py`, `movement.py`, `assignment.py`, `pickup.py`, `delivery.py`, `idle.py` | Per-round decisions, order management |
| qa-agent | `tests/`, `simulator.py`, `benchmark.py`, `docs/benchmark_results.md` | Testing, benchmarking, profiling |

Shared (read-only for agents): `bot.py`, `docs/CHALLENGE.md`

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
```

**IMPORTANT for agents**: Always pipe pytest output through `tail` to avoid flooding your context with hundreds of lines. Use `-q --tb=line` by default, only switch to `--tb=short` when debugging a specific failure. Never use `-v` — it generates excessive output that wastes context memory.
