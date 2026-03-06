# Strategy Agent

## Role

Expert game strategy and decision engineer. Owns all per-round decision logic — when to pick up, deliver, pre-pick, yield, or wait. Optimizes scoring across the full game.

## Coordination

**Before starting**: Read `TASKS.md`, claim an open task assigned to you, update its status to `in-progress`. Do NOT start work without claiming a task first. Check `Depends on` — if a task depends on another that isn't `done`, pick a different task.

## Owned Files

| File | Scope |
|------|-------|
| `round_planner.py` | Per-round bot decisions, order management, preview pipelining |

**Do NOT modify**: `bot.py`, `pathfinding.py`, `game_state.py`, `simulator.py`, `test_bot.py`

## Reference

- `docs/CHALLENGE.md` — full game spec, protocol, scoring rules
- `docs/OPTIMIZATION_PLAN.md` — phases 2, 4
- `docs/NEXT_STEPS.md` — implementation progress
- MCP server: `claude mcp add --transport http grocery-bot https://mcp-docs.ainm.no/mcp`

## Current State

Already implemented in `RoundPlanner`:
- 7-step per-bot decision pipeline (`_decide_bot`)
- Active item pickup with TSP routing and multi-bot assignment
- Preview pipelining (adjacent free pickups + detour pickups)
- Order nearly-complete detection (suppresses preview detours)
- Endgame rush (last 30 rounds)
- Yield-to system for higher-urgency bots
- Dropoff area clearing for idle bots
- Pickup failure detection and blacklisting

### Decision Pipeline (current)

```
Step 1: At drop-off with active items -> deliver
Step 2: All active picked up -> rush to deliver (optional preview detour)
Step 3: Adjacent preview pickup (free) / inventory full -> deliver
Step 3b: Endgame rush if no time for more pickups
Step 4: Pick up active items (adjacent -> assigned route -> greedy TSP)
Step 5: Deliver active items (optional preview detour if not nearly complete)
Step 6: Pre-pick preview items
Step 7: Clear dropoff area when idle
```

## Tasks

### Priority 1: Smarter Dropoff Timing (Phase 4.4)

Current logic delivers only when inventory full (3) or all active items picked. Improve:

**Deliver early if it completes the order:**
```python
# In _decide_bot, before Step 4:
# Check if items in inventory + items_delivered == items_required
# If yes, rush to drop-off immediately (triggers +5 bonus + unlocks next order)
```

**Deliver when passing dropoff anyway:**
```python
# In Step 4 navigation: if next BFS step toward item passes through drop-off
# and bot has active items, do drop_off action instead of moving through
```

**Don't deliver partial items on detour:**
- Only deliver if bot is AT drop-off or path to next item goes THROUGH drop-off
- Never make a dedicated trip just to deliver 1 item that won't complete the order

### Priority 2: Item Proximity Clustering (Phase 4.2)

When choosing between same-type items, prefer the one closer to other needed items:

```python
def _score_item_by_cluster(self, item, pos, remaining_needed):
    """Score = distance_to_item + avg_distance_from_item_to_other_needed_items.

    Picks items that minimize total route, not just next-step distance.
    """
```

- Compute center-of-mass of all remaining needed item positions
- Use as tiebreaker when multiple same-type items have similar distance
- Apply in `_build_greedy_route` candidate selection

### Priority 3: Dedicated Preview Bot (Phase 2.2)

For 2+ bots when active order is nearly complete:

```python
def _assign_preview_bot(self):
    """Designate one bot to exclusively pre-pick preview items.

    Triggered when order_nearly_complete and len(bots) >= 2.
    Picks the bot furthest from remaining active items.
    """
```

- Chosen bot skips Steps 4-5 entirely, goes straight to Step 6 (preview pre-pick)
- Walks to preview items, not just adjacent free pickups
- When active order completes, this bot may already hold cascade-ready items
- Only one preview bot at a time — others still focus on active order

### Priority 4: Improved End-Game (Phase 4.3)

Current endgame is just "rush delivery in last 30 rounds". Make it smarter:

```python
def _endgame_decision(self, bot, pos, inv):
    """Calculate whether to continue picking or switch to maximize-items mode.

    If rounds_to_complete_order > rounds_remaining:
      - Still deliver what we have (+1 per item)
      - Pick up nearby items only if pickup + delivery fits in remaining rounds
      - Don't start long trips that can't complete
    """
```

- Dynamic endgame threshold based on remaining order size (not fixed 30 rounds)
- `rounds_to_complete = sum(dist_to_each_remaining_item + delivery_trips)`
- If order can't complete, maximize raw item deliveries instead

## Scoring Model

Understanding the math drives all decisions:

```
order_value = len(items_required) + 5    # items + completion bonus
per_item = 1 point
completion_bonus = 5 points

Example: 4-item order = 9 points if completed, 0-4 if partial
-> Always prioritize completing orders over starting new pickups
-> Last item of an order is worth 6 points (1 + 5 bonus)
```

## Constraints

- `RoundPlanner` is instantiated fresh each round — no state persists (use `GameState` for that)
- Bot processing order matters — lower ID first, predicted positions used for collision
- `_spare_slots(inv)` = `(3 - len(inv)) - active_on_shelves` — don't reserve slots needed for active items
- The `_claim` system prevents multiple bots targeting the same item in one round
- `max_claim` distributes items fairly across idle bots

## Testing

```sh
python -m pytest test_bot.py -v
```

Test scenarios to add:
- Bot delivers early when it would complete the order
- Bot delivers when passing through drop-off en route
- Proximity clustering picks the globally-better item
- Preview bot assignment triggers at the right time
- Endgame correctly switches to maximize-items mode
