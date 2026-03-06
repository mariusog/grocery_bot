# Next Development Steps

## Simulator Scores (2026-03-05)

| Map | Bots | Before | Phase 2 | Phase 3 | Change |
|-----|------|--------|---------|---------|--------|
| Easy | 1 | 118 | 121.8 | **127.8** | +9.8 |
| Medium | 2 | 116 | 122.2 | **110.3** | -5.7* |
| Hard | 5 | 96 | 120.8 | **123.0** | +27.0 |
| Expert | 10 | 67 | 106.4 | **115.8** | +48.8 |

*Medium has outlier seeds (12=27, 13=43) from preview-item deadlocks not yet fully resolved.

---

## Architecture

```
bot.py             — thin orchestrator, WebSocket game loop, re-exports
pathfinding.py     — BFS variants, temporal BFS, movement helpers
game_state.py      — GameState class (caches, TSP, Hungarian, interleaved routing)
round_planner.py   — RoundPlanner (per-round decisions for all bots)
simulator.py       — local game simulator with difficulty presets + diagnostics
benchmark.py       — performance benchmarking script
test_bot.py        — 129 tests (including score regression suite)
```

---

## Implemented Features

### Core (Steps 1-8)
- Distance matrix & caching, TSP routing, multi-trip planning
- Preview pipelining with cascade-aware type selection
- Anti-collision: predicted positions, yield-to, unstick fallback
- End-game filter, pickup failure blacklisting
- Zone assignment for 5+ bots

### Phase 2: Congestion Fixes
- **Temporal BFS** integrated via `_bfs_smart()` — avoids predicted positions
- **Oscillation detection** via bot_history deque(maxlen=3)
- **Idle positioning** — score-based dispersal from dropoff + other bots
- **Aisle traffic staggering** — reassigns bots targeting same column
- **Reduced blocking radius** — Manhattan dist 6 for 5+ bots
- **Diagnostics** — simulator diagnose mode, profile_congestion()

### Phase 3: Routing Optimization
- **Round-trip cost scoring** — `_build_greedy_route` scores by `d + d_drop` instead of just `d`
- **Cluster tiebreaker** reduced to 0.3 weight
- **Preview pickup guard** — single bot skips preview when active items remain
- **Preview deadlock fix** — bots with non-active inventory deliver to free slots (≤3 bots)
- **Preview bot adjacent active pickup** — preview bots pick up adjacent active items
- **Alternative cell routing** — falls back to other adjacent cells when primary target blocked

---

## Not Yet Integrated

| Feature | Module | Why Not Yet |
|---------|--------|-------------|
| Interleaved delivery | `game_state.py` | RoundPlanner doesn't call it yet |
| Hungarian assignment | `game_state.py` | RoundPlanner still uses greedy |
| Deliver-vs-fill decision | `round_planner.py` | `_should_deliver_early` exists but hurt benchmarks |

---

## Next Priorities

| Priority | Feature | Expected Impact | Effort |
|----------|---------|----------------|--------|
| 1 | Fix remaining Medium deadlocks (seeds 12,13,15) | +15 Medium avg | Medium |
| 2 | Wire Hungarian assignment | Better multi-bot distribution | Low |
| 3 | Wire interleaved delivery | Fewer wasted trips | Medium |
| 4 | Tune deliver-vs-fill heuristic | +5 Easy/Medium | Medium |
| 5 | Expert-specific tuning | 10-bot coordination polish | High |

**Target**: Easy 140+, Medium 130+, Hard 140+, Expert 130+
