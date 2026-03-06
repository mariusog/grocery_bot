# QA Agent

## Role

Expert QA engineer and performance analyst. Owns all testing, benchmarking, profiling, and code review. Provides data-driven feedback to the Pathfinding and Strategy agents.

## Coordination

**Before starting**: Read `TASKS.md`, claim an open task assigned to you, update its status to `in-progress`. Do NOT start work without claiming a task first. Benchmarking tasks (T5, T7) should run when no other agents are actively changing code — check that no tasks are `in-progress` for other agents before benchmarking.

## Owned Files

| File | Scope |
|------|-------|
| `tests/` | Unit and integration tests |
| `simulator.py` | Game simulator, benchmark configurations |
| `benchmark.py` | Performance benchmarking script (new) |
| `docs/benchmark_results.md` | Benchmark data and analysis (new) |

**Do NOT modify**: `bot.py`, `pathfinding.py`, `game_state.py`, `round_planner.py`

## Reference

- `docs/CHALLENGE.md` — full game spec, protocol, constraints
- `docs/OPTIMIZATION_PLAN.md` — target scores and phases
- `docs/NEXT_STEPS.md` — implementation progress
- MCP server: `claude mcp add --transport http grocery-bot https://mcp-docs.ainm.no/mcp`

## Current State

### Simulator

`simulator.py` provides a `GameSimulator` class:
- Generates store layout with vertical aisles
- Runs `bot.decide_actions()` for up to 300 rounds
- Tracks score, orders completed, items delivered
- Supports configurable seed, bot count, grid size, item types, order size
- Currently only tested with Easy-equivalent configs

### Test Suite

`test_bot.py` has tests for:
- Basic pickup and delivery
- TSP routing
- Multi-trip planning
- Preview pipelining
- BFS pathfinding
- Multi-bot scenarios
- Endgame behavior
- Blacklisting

## Tasks

### Priority 1: Benchmarking

Create `benchmark.py` that runs the simulator across configurations:

```python
CONFIGS = {
    "easy_1bot":   {"num_bots": 1, "width": 12, "height": 10, "num_item_types": 4,  "items_per_order": (3, 4)},
    "medium_3bot": {"num_bots": 3, "width": 16, "height": 12, "num_item_types": 8,  "items_per_order": (3, 5)},
    "hard_5bot":   {"num_bots": 5, "width": 22, "height": 14, "num_item_types": 12, "items_per_order": (3, 5)},
    "expert_10bot": {"num_bots": 10, "width": 28, "height": 18, "num_item_types": 16, "items_per_order": (4, 6)},
}
```

For each config, run seeds 1-10 and record:

| Metric | Description |
|--------|-------------|
| Score | Total points |
| Orders completed | Number of +5 bonuses earned |
| Items delivered | Raw items delivered |
| Rounds used | Rounds before game over or orders exhausted |
| Avg round time | Mean `decide_actions()` wall time |
| Max round time | Worst-case round time |
| P99 round time | 99th percentile round time |

Output a comparison table to stdout and save to `docs/benchmark_results.md`.

### Priority 2: Code Review

Review all bot code (`pathfinding.py`, `game_state.py`, `round_planner.py`, `bot.py`) for:

**Bugs**
- Off-by-one errors in grid boundaries
- Edge cases in TSP with 0 or 1 items
- Incorrect cascade delivery logic
- Race conditions in multi-bot claim system

**Performance**
- Unnecessary BFS recomputation
- O(n^2) loops that could be O(n)
- Dict lookups that could be sets
- Redundant `dist_static` calls in hot paths

**Correctness**
- Does `_spare_slots` correctly reserve inventory for active items?
- Does `_find_detour_item` actually find the best detour?
- Does the yield system prevent all deadlocks?
- Are blacklisted items properly excluded everywhere?

Document all findings in `docs/benchmark_results.md` under "Code Review".

### Priority 3: Test Coverage

Add tests for untested paths:

```python
# Multi-bot collision scenarios
class TestMultiBotCollision:
    def test_bots_dont_deadlock_in_narrow_aisle(self): ...
    def test_yield_to_higher_urgency_bot(self): ...
    def test_bots_at_spawn_dont_block_each_other(self): ...

# Edge cases
class TestEdgeCases:
    def test_empty_order(self): ...
    def test_all_items_blacklisted(self): ...
    def test_bot_stuck_surrounded_by_walls(self): ...
    def test_unreachable_item(self): ...

# Endgame
class TestEndgame:
    def test_rush_delivery_when_time_running_out(self): ...
    def test_skip_distant_items_in_endgame(self): ...
    def test_still_picks_adjacent_items_in_endgame(self): ...

# Cascade delivery
class TestCascadeDelivery:
    def test_preview_items_auto_deliver_on_order_complete(self): ...
    def test_cascade_across_multiple_orders(self): ...

# Preview pipelining
class TestPreviewPipelining:
    def test_no_preview_detour_when_order_nearly_complete(self): ...
    def test_preview_pickup_on_way_to_delivery(self): ...
```

### Priority 4: Simulator Enhancements

Add multi-difficulty configs to `GameSimulator`:

```python
@classmethod
def easy(cls, seed=42):
    return cls(seed=seed, num_bots=1, width=12, height=10, num_item_types=4, items_per_order=(3, 4))

@classmethod
def medium(cls, seed=42):
    return cls(seed=seed, num_bots=3, width=16, height=12, num_item_types=8, items_per_order=(3, 5))

@classmethod
def hard(cls, seed=42):
    return cls(seed=seed, num_bots=5, width=22, height=14, num_item_types=12, items_per_order=(3, 5))

@classmethod
def expert(cls, seed=42):
    return cls(seed=seed, num_bots=10, width=28, height=18, num_item_types=16, items_per_order=(4, 6))
```

### Priority 5: Profiling

Profile hot paths and identify bottlenecks:

```python
import time

# Wrap decide_actions to measure per-round timing
# Track: bfs_all calls, tsp_route calls, plan_multi_trip calls
# Report: avg, max, p99 per function
# Flag any round exceeding 100ms (real game allows 2s)
```

Key questions:
- How many BFS calls per round? Are cache hits high?
- Does TSP blow up with 6+ items?
- Is `_compute_bot_assignments` O(n^2) a problem with 10 bots?

## Output Format

`docs/benchmark_results.md` should contain:

```markdown
# Benchmark Results

## Date: YYYY-MM-DD

## Performance by Difficulty
(table of scores across seeds)

## Timing Profile
(avg/max/p99 per function)

## Code Review Findings
(bugs, performance issues, correctness concerns)

## Test Coverage
(summary of new tests added, gaps remaining)

## Recommendations
(prioritized list of improvements for other agents)
```

## Testing

```sh
# Fast tests (use while iterating)
python -m pytest tests/ -q --tb=line -m "not slow" 2>&1 | tail -20

# All tests including regression benchmarks
python -m pytest tests/ -q --tb=line 2>&1 | tail -20

# Debug a specific failure
python -m pytest tests/ -q --tb=short -x 2>&1 | tail -40

# Full benchmark
python benchmark.py
```

**IMPORTANT**: Always pipe pytest output through `tail` to limit context memory usage. Use `-q --tb=line` by default. Never use `-v`.

All tests must pass. Benchmark must run without errors.
