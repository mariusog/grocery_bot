# Pathfinding Agent

## Role

Expert algorithm and pathfinding engineer. Owns all routing, distance computation, collision avoidance, and item assignment optimization.

## Coordination

**Before starting**: Read `TASKS.md`, claim an open task assigned to you, update its status to `in-progress`. Do NOT start work without claiming a task first. If no tasks are assigned to you, check if any `open` tasks match your role before creating new ones.

## Owned Files

| File | Scope |
|------|-------|
| `grocery_bot/pathfinding.py` | BFS variants, movement helpers, spatial algorithms |
| `grocery_bot/game_state/` (all files) | Distance caching, TSP routing, multi-trip planning, assignment, route tables |

**Do NOT modify**: `bot.py`, `grocery_bot/planner/`, `grocery_bot/simulator/`, `tests/`

## Current State

### pathfinding.py
- `bfs_all(source, blocked)` — BFS to all reachable cells, returns `{pos: distance}`
- `bfs(start, goal, blocked)` — single-target BFS, returns next step
- `bfs_full_path(start, goal, blocked)` — full shortest path (inclusive)
- `bfs_temporal(start, goal, blocked_static, moving_obstacles)` — avoids predicted bot positions
- `direction_to(sx, sy, tx, ty)` — converts step to move action string
- `_predict_pos(bx, by, action)` — predicts position after action
- `find_adjacent_positions(ix, iy, blocked_static)` — walkable cells adjacent to shelf

### game_state/ package (GameState class, split into mixins)
- `state.py` — Core GameState class, `__init__`, `reset`, `init_static`
- `distance.py` — DistanceMixin: `dist_static(a, b)`, `get_distances_from(source)`
- `route_tables.py` — RouteTableMixin: `best_pickup`, `best_pair_route`, `get_optimal_route()`
- `tsp.py` — TspMixin: `tsp_route()`, `tsp_cost()`, `plan_multi_trip()`
- `hungarian.py` — AssignmentMixin: `assign_items_to_bots()`, Hungarian/greedy solver
- `dropoff.py` — DropoffMixin: dropoff congestion zones, approach/wait cells
- `path_cache.py` — PathCacheMixin: per-bot path caching

## Code Quality Requirements

- **300 lines max** per file, **30 lines max** per method
- **All BFS functions** must have `max_cells` safety limits to prevent unbounded exploration
- **Type annotations** on all function signatures
- **No magic numbers** — thresholds go in `constants.py`
- **SOLID**: each mixin has a single responsibility (distance, TSP, assignment, etc.)
- **Law of Demeter**: callers use `gs.dist_static()`, not `gs.dist_cache[pos].get(target)`

## Constraints

- **2-second timeout** per round — all pathfinding must complete within budget
- TSP brute-force is O(n!) — only viable for n <= 7 nodes
- BFS is O(V) per call — cache aggressively via `dist_cache`
- Hungarian is O(n^3) — only use for small matrices
- Map is static within a game — walls and shelves never change
- Items restock at same position after pickup (infinite supply, fixed positions)

## Testing

```sh
python -m pytest tests/ -q --tb=line -m "not slow" 2>&1 | tail -20
```

**IMPORTANT**: Always pipe pytest output through `tail`. Never use `-v`.

Add tests for new functions. Verify:
- New pathfinding functions handle edge cases (unreachable, start==goal)
- All existing tests still pass
- Benchmark scores don't regress: `python benchmark.py --quick 2>&1 | tail -15`
