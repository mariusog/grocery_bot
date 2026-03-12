# Oracle Game Planner — Design Document

## Overview

The Oracle Planner exploits the deterministic nature of the game: same day = same
map + same order sequence. By recording orders across multiple runs, we build
complete knowledge of the order pipeline and can pre-plan the entire game.

## Architecture

```
bot.py: decide_actions()
  ├─ oracle knowledge >= 4 orders? ──Yes──> OraclePlanner
  │                                           │
  │                                      OracleScheduler
  │                                      (global plan)
  │                                           │
  │                                      Execute schedule
  │                                      (per-round actions)
  └─ No ──> RoundPlanner (existing 22-step chain, unchanged)
```

### Shared Infrastructure (from GameState)
- `gs.dist_static(a, b)` — cached BFS distances
- `gs.blocked_static` — wall/obstacle set
- `gs.future_orders` — the oracle order list
- `gs.tsp_route()` — TSP solver for pickup routing
- `gs.assign_items_to_bots()` — Hungarian assignment
- BFS pathfinding from `pathfinding.py`

### New Components
- `oracle_types.py` — `BotTask`, `OrderPlan`, `Schedule` dataclasses
- `oracle_scheduler.py` — `OracleScheduler`: builds global multi-order plan
- `oracle_planner.py` — `OraclePlanner`: per-round action executor

## Algorithm

### Phase A: Schedule Construction (OracleScheduler)

Runs once at game start and on replan triggers. Produces a `Schedule`.

**Input**: Future orders, bot positions, item positions on map.

**Steps**:
1. For each order K (active through planning horizon):
   - Identify needed items from `order["items_required"]`
   - Match item types to physical item instances on the map
   - Assign items to bots using Hungarian algorithm with **projected positions**
   - Each bot gets at most 3 items (inventory limit)
   - Compute TSP pickup route per bot → delivery to dropoff
2. Pipeline overlap: While deliverers handle order K, idle bots start picking K+1
3. Delivery staggering: Max 2 bots approach dropoff simultaneously

**Output**: `Schedule` with per-bot task queues spanning multiple orders.

### Phase B: Per-Round Execution (OraclePlanner.plan())

Each round translates the schedule into concrete actions:

1. **Replan triggers**:
   - Order completed → advance pipeline, reassign freed bots
   - Bot stuck 5+ rounds → replan that bot
   - New orders discovered → extend schedule
   - Schedule >20 rounds old → full replan

2. **Per-bot action** (priority list):
   - At dropoff + has active items → `drop_off`
   - Full load of active items → move toward dropoff
   - Adjacent to assigned pickup → `pick_up`
   - Has assigned items → move toward next pickup
   - Spare slots + preview items → pick preview
   - No current task → move toward projected future position
   - Fallback → `wait`

3. **Collision avoidance**: BFS with temporal blocked set.

### Phase C: Partial Oracle Fallback

| Knowledge Level | Behavior |
|----------------|----------|
| All orders known | Full oracle scheduling |
| 4+ orders known | Oracle for known, then RoundPlanner |
| <4 orders known | RoundPlanner entirely |

## Data Structures

```python
@dataclass
class BotTask:
    bot_id: int
    task_type: str          # "pick", "deliver", "move_to"
    target_pos: tuple[int, int]
    item_id: str | None     # for pickup tasks
    item_type: str | None
    order_idx: int

@dataclass
class OrderPlan:
    order_idx: int
    items_required: list[str]
    item_assignments: dict[str, int]   # item_id -> bot_id
    estimated_rounds: int

@dataclass
class Schedule:
    order_plans: list[OrderPlan]
    bot_queues: dict[int, list[BotTask]]
    horizon: int
    created_round: int
```

## Constants

| Constant | Value | Purpose |
|----------|-------|---------|
| ORACLE_PLANNER_ENABLED | True | Feature flag |
| ORACLE_MIN_KNOWN_ORDERS | 4 | Min future orders to activate |
| ORACLE_PLANNING_HORIZON | 20 | Max orders to plan ahead |
| ORACLE_REPLAN_INTERVAL | 20 | Rounds between refreshes |
| ORACLE_STUCK_THRESHOLD | 5 | Rounds stuck before replanning |
| ORACLE_PIPELINE_DEPTH | 2 | Orders worked simultaneously |
| ORACLE_MAX_DELIVERY_SLOTS | 2 | Max simultaneous deliverers |

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| New pipeline vs modify existing | New pipeline | 22-step chain is fragile |
| Own movement vs MovementMixin | Own simple movement | MovementMixin deeply coupled to step chain |
| Schedule once vs per-round | Schedule once + replan | Per-round optimization too expensive |
| Pipeline depth | 2 (active + preview) | Can only deliver active items |
| Projected positions | Yes | Assigning by current position is wrong |
