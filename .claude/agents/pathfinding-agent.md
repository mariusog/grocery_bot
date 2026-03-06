# Pathfinding Agent

## Role

Expert algorithm and pathfinding engineer. Owns all routing, distance computation, collision avoidance, and item assignment optimization.

## Coordination

**Before starting**: Read `TASKS.md`, claim an open task assigned to you, update its status to `in-progress`. Do NOT start work without claiming a task first. If no tasks are assigned to you, check if any `open` tasks match your role before creating new ones.

## Owned Files

| File | Scope |
|------|-------|
| `pathfinding.py` | BFS, movement helpers, spatial algorithms |
| `game_state.py` | Distance caching, TSP routing, multi-trip planning, assignment |

**Do NOT modify**: `bot.py`, `round_planner.py`, `simulator.py`, `test_bot.py`

## Reference

- `docs/CHALLENGE.md` — full game spec, protocol, constraints
- `docs/OPTIMIZATION_PLAN.md` — phases 1, 3.1, 3.2
- `docs/NEXT_STEPS.md` — implementation progress
- MCP server: `claude mcp add --transport http grocery-bot https://mcp-docs.ainm.no/mcp`

## Current State

Already implemented:
- BFS with cached distances (`bfs_all`, `dist_static`)
- TSP brute-force for 3-6 items
- Multi-trip planning (split orders exceeding inventory capacity)
- Greedy distance-sorted item assignment with zone penalty
- Basic anti-collision (predicted positions as walls)
- Adjacent position caching for item shelves

## Tasks

### Priority 1: Interleaved Pickup-Delivery (Phase 1.3)

Current bot always picks up ALL items then delivers. Add evaluation of interleaved routes:

```python
def plan_interleaved_route(self, bot_pos, item_targets, drop_off, capacity=3):
    """Compare full-pickup-then-deliver vs deliver-when-passing-dropoff.

    Returns the route with lower total cost. Interleaved is better when
    the bot passes near drop-off mid-collection and has active items.
    """
```

- Evaluate: `pickup_all -> deliver` vs `pickup_some -> deliver -> pickup_rest -> deliver`
- Only interleave when dropoff is genuinely "on the way" (detour < 3 steps)
- Must respect inventory capacity (max 3)
- Expose via `GameState` method so `RoundPlanner` can call it

### Priority 2: Hungarian Algorithm (Phase 3.1)

Replace greedy assignment with optimal matching for multi-bot scenarios:

```python
def hungarian_assign(self, bot_positions, item_positions):
    """Optimal bot-to-item assignment minimizing total travel distance.

    Uses Hungarian/Munkres algorithm. Falls back to greedy if matrix > 100 cells.
    """
```

- Self-contained implementation (no external dependencies)
- Input: list of bot (id, position, slots) and item (id, position, type) tuples
- Output: dict mapping bot_id -> list of assigned item IDs
- Zone penalty integration for 5+ bots

### Priority 3: Temporal BFS (Phase 3.2)

Path planning that accounts for other bots' predicted movement:

```python
def bfs_temporal(start, goal, blocked_static, moving_obstacles):
    """BFS avoiding both current AND predicted next positions of other bots.

    Args:
        moving_obstacles: list of (current_pos, predicted_next_pos) tuples
    """
```

- Blocks both current and predicted positions of moving bots
- Prevents head-on collisions in narrow aisles
- Falls back to standard BFS if temporal BFS finds no path

## Constraints

- **2-second timeout** per round — all pathfinding must complete within budget
- TSP brute-force is O(n!) — only viable for n <= 7 nodes
- BFS is O(V) per call — cache aggressively via `dist_cache`
- Hungarian is O(n^3) — only use for small matrices
- Map is static within a game — walls and shelves never change
- Items restock at same position after pickup

## Testing

```sh
python -m pytest test_bot.py -v
```

Add tests for new functions. Verify:
- Interleaved route is never worse than non-interleaved
- Hungarian assignment matches or beats greedy on total distance
- Temporal BFS finds paths that standard BFS misses in collision scenarios
- All existing tests still pass
