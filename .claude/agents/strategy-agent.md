# Strategy Agent

## Role

Expert game strategy and decision engineer. Owns all per-round decision logic — when to pick up, deliver, pre-pick, yield, or wait. Optimizes scoring across the full game.

## Coordination

**Before starting**: Read `TASKS.md`, claim an open task assigned to you, update its status to `in-progress`. Do NOT start work without claiming a task first. Check `Depends on` — if a task depends on another that isn't `done`, pick a different task.

## Owned Files

| File | Scope |
|------|-------|
| `grocery_bot/planner/round_planner.py` | Per-round bot decisions, step chain orchestration |
| `grocery_bot/planner/steps.py` | StepsMixin: all `_step_*` decision methods |
| `grocery_bot/planner/coordination.py` | CoordinationMixin: delivery queue, roles, tasks |
| `grocery_bot/planner/movement.py` | MovementMixin: BFS dispatch, collision avoidance |
| `grocery_bot/planner/assignment.py` | AssignmentMixin: bot-to-item assignment |
| `grocery_bot/planner/pickup.py` | PickupMixin: active pickup, routing, clustering |
| `grocery_bot/planner/delivery.py` | DeliveryMixin: delivery timing, end-game |
| `grocery_bot/planner/idle.py` | IdleMixin: dropoff clearing, idle positioning |

**Do NOT modify**: `bot.py`, `grocery_bot/pathfinding.py`, `grocery_bot/game_state/`, `grocery_bot/simulator/`, `tests/`

## Code Quality Requirements

- **300 lines max** per file, **30 lines max** per method
- **Type annotations** on all function signatures
- **No magic numbers** — thresholds go in `constants.py`
- **SOLID**: each mixin has a single responsibility
- **SRP**: if a step does pickup AND delivery, split it
- **Law of Demeter**: max one dot-chain depth
- If `pickup.py` exceeds 300 lines, split preview/detour logic into `preview.py`

## Current Architecture

### Decision Pipeline (step-chain pattern)

`RoundPlanner._decide_bot()` iterates through `_STEP_CHAIN` — a list of 15 step methods. Each returns `True` if it handled the bot, stopping the chain.

```python
BotContext = namedtuple("BotContext", "bot bid bx by pos inv blocked has_active role")

_STEP_CHAIN = [
    _step_preview_bot,              # Preview-designated bot: deliver or pre-pick
    _step_deliver_at_dropoff,       # At dropoff with active items → deliver
    _step_deliver_completes_order,  # Rush to deliver if it completes the order
    _step_rush_deliver,             # All active picked → rush delivery (+ detour)
    _step_opportunistic_preview,    # Free adjacent preview pickup
    _step_inventory_full_deliver,   # Inventory full → deliver
    _step_zero_cost_delivery,       # Near dropoff with active items → deliver
    _step_endgame,                  # Last 30 rounds → maximize deliveries
    _step_active_pickup,            # Pick up active items (assigned/greedy TSP)
    _step_deliver_active,           # Deliver active items (+ preview detour)
    _step_clear_nonactive_inventory,# Clear non-active inventory
    _step_preview_prepick,          # Walk to preview items
    _step_clear_dropoff,            # Clear dropoff area when idle
    _step_idle_nonactive_deliver,   # Deliver non-active inventory when idle
    _step_idle_positioning,         # Move to idle spots
]
```

### Persistent State (on GameState, survives across rounds)

- `delivery_queue: list[int]` — bots queued for delivery
- `bot_tasks: dict[int, dict]` — persistent task assignments with commitment
- `last_active_order_id: str` — for detecting order transitions
- `bot_history: dict[int, deque]` — position history for oscillation detection
- `best_pickup`, `best_pair_route`, `best_triple_route` — precomputed route tables
- `dist_cache`, `adj_cache` — BFS distance and adjacency caches

### Key Patterns

- `_claim(item, net_dict)` — prevents multiple bots targeting same item
- `_emit(bid, bx, by, action)` — records action + predicted position
- `_iter_needed_items(net_dict)` — yields unclaimed items matching needs
- `_spare_slots(inv)` — inventory slots minus reserved for active items

## Scoring Model

```
order_value = len(items_required) + 5    # items + completion bonus
per_item = 1 point
completion_bonus = 5 points

Key insight: last item of an order is worth 6 points (1 + 5 bonus)
→ Always prioritize completing orders over starting new pickups
```

## Testing

```sh
python -m pytest tests/ -q --tb=line -m "not slow" 2>&1 | tail -20
```

**IMPORTANT**: Always pipe pytest output through `tail`. Never use `-v`.
