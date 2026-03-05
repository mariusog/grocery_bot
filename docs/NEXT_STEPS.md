# Next Development Steps

## Live Scores (2026-03-05)

| Map | Grid | Bots | Score | Orders | Items |
|-----|------|------|-------|--------|-------|
| Easy | 12x10 | 1 | 118 | — | — |
| Medium | 16x12 | 3 | **116** | 13 | 51 |
| Hard | 22x14 | 5 | **96** | 11 | 41 |
| Expert | 28x18 | 10 | **67** | 6 | 37 |
| **Total** | | | **397** | | |

---

## Architecture

```
bot.py             — thin orchestrator, WebSocket game loop, re-exports
pathfinding.py     — BFS variants, temporal BFS, movement helpers
game_state.py      — GameState class (caches, TSP, Hungarian, interleaved routing)
round_planner.py   — RoundPlanner (per-round decisions for all bots)
simulator.py       — local game simulator with difficulty presets
benchmark.py       — performance benchmarking script
test_bot.py        — 106 tests
```

---

## Implemented Features

### Core (Steps 1-6)
- **Distance matrix & caching** — BFS results cached per source; O(1) lookups via `dist_static()`
- **TSP-optimal pickup ordering** — brute-force permutations for 3-6 item routes
- **Multi-trip planning** — splits orders exceeding inventory capacity into optimal trip pairs
- **Preview pipelining** — opportunistic and detour-based preview pickups; cascade-aware type selection
- **Anti-collision** — predicted positions as walls, yield-to system, unstick fallback
- **End-game filter** — skips items that can't be picked up and delivered in remaining rounds
- **Pickup failure detection** — blacklists items that fail pick_up 3+ times
- **GameState class** — encapsulates all persistent state and caches
- **Zone assignment** — vertical zone penalty for 5+ bots to reduce cross-traffic

### Phase 1.3: Interleaved Pickup-Delivery — DONE
- `GameState.plan_interleaved_route()` compares full-pickup vs batch-split delivery
- Evaluates all possible splits, picks the one with lowest total travel cost
- Not yet wired into RoundPlanner (available for future integration)

### Phase 3.1: Hungarian Algorithm — DONE
- `GameState.hungarian_assign()` with O(n^3) Munkres implementation
- Falls back to greedy for >100 bot-item pairs
- Not yet wired into RoundPlanner (available for future integration)

### Phase 3.2: Temporal BFS — DONE
- `bfs_temporal()` avoids both current AND predicted positions of other bots
- Two-step model: step 0 blocks both, step 1+ blocks only predicted
- Falls back to standard BFS if temporal path blocked
- Not yet wired into RoundPlanner (available for future integration)

### Phase 4.4: Smart Dropoff Timing — DONE
- Delivers early if bot's items alone complete the order (+5 bonus rush)
- Zero-cost delivery when adjacent to dropoff and next item is via dropoff
- Never detours just to deliver partial items that won't complete order

### Phase 4.2: Item Proximity Clustering — DONE
- `_cluster_select()` scores items by `bot_distance + 0.5 * center_of_mass_distance`
- Picks items that minimize total route, not just next-step distance

### Phase 2.2: Dedicated Preview Bot — DONE
- For 2 bots when order nearly complete, assigns furthest bot to pre-pick preview items
- Preview bot skips active items entirely, focuses on next order

### Phase 4.3: Improved End-Game — DONE
- `_estimate_rounds_to_complete()` calculates greedy tour for remaining items
- Switches to maximize-items mode when order can't complete in time
- Dynamic decision: grab one more item vs deliver now

### Anti-Deadlock & Crowd Dispersal — DONE
- BFS goal-in-blocked-set check prevents moving into occupied cells
- Idle bots actively move away from crowded areas (Step 8)
- Fixed BFS start-position blocking for co-located bots at spawn

---

## Not Yet Integrated (algorithms ready, not wired in)

| Feature | Module | Why Not Yet |
|---------|--------|-------------|
| Interleaved delivery | `game_state.py` | RoundPlanner doesn't call it yet |
| Hungarian assignment | `game_state.py` | RoundPlanner still uses greedy |
| Temporal BFS | `pathfinding.py` | RoundPlanner uses standard BFS |
| `bfs_full_path()` | `pathfinding.py` | Available for path-through-dropoff detection |

Integrating these into `round_planner.py` is the next high-impact work.

---

## Next Priorities

| Priority | Feature | Expected Impact | Effort |
|----------|---------|----------------|--------|
| 1 | Wire temporal BFS into RoundPlanner | Reduce 5+ bot deadlocks | Low |
| 2 | Wire Hungarian assignment into RoundPlanner | Better multi-bot distribution | Low |
| 3 | Wire interleaved delivery into RoundPlanner | Fewer wasted trips | Medium |
| 4 | Path-through-dropoff detection | Zero-cost partial deliveries | Medium |
| 5 | Better spawn exit strategy | Faster first-round dispersal | Low |
| 6 | Expert-specific tuning | 10-bot coordination polish | High |

**Target**: Easy 130+, Medium 150+, Hard 150+, Expert 150+
