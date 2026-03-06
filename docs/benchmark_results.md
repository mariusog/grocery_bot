# Benchmark Results

Generated: 2026-03-06 (post-refactor, all tasks complete)

## Performance Summary (seeds 1-20)

| Difficulty | Bots | Avg Score | Min | Max | Avg Time/game |
|------------|------|-----------|-----|-----|---------------|
| Easy       | 1    | 152.6     | 140 | 163 | 0.014s        |
| Medium     | 3    | 104.3     | 33  | 134 | 0.051s        |
| Hard       | 5    | 76.2      | 45  | 98  | 0.113s        |
| Expert     | 10   | 45.3      | 11  | 75  | 0.283s        |

## Comparison to Live Server (2026-03-06)

| Difficulty | Live Score | Sim Avg | Gap  |
|------------|------------|---------|------|
| Easy       | 133        | 152.6   | +15% |
| Medium     | 110        | 104.3   | -5%  |
| Hard       | 70         | 76.2    | +9%  |
| Expert     | 46         | 45.3    | -2%  |

Simulator now tracks within ~5-15% of live server (was 22-50% before T11 wall fixes).

## Per-Seed Scores

### Easy (1 bot)

| Seed | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 |
|------|---|---|---|---|---|---|---|---|---|----|----|----|----|----|----|----|----|----|----|----|
| Score | 140 | 145 | 153 | 146 | 152 | 148 | 163 | 161 | 155 | 144 | 157 | 148 | 146 | 156 | 153 | 162 | 148 | 151 | 163 | 160 |

### Medium (3 bots)

| Seed | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 |
|------|---|---|---|---|---|---|---|---|---|----|----|----|----|----|----|----|----|----|----|----|
| Score | 93 | 112 | 95 | 115 | 129 | 122 | 90 | 33 | 119 | 103 | 100 | 111 | 109 | 120 | 52 | 108 | 98 | 113 | 134 | 130 |

Outliers: seed 8 (33), seed 15 (52) — likely deadlock or bad layout.

### Hard (5 bots)

| Seed | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 |
|------|---|---|---|---|---|---|---|---|---|----|----|----|----|----|----|----|----|----|----|----|
| Score | 84 | 45 | 64 | 98 | 83 | 58 | 81 | 72 | 90 | 73 | 65 | 63 | 92 | 80 | 96 | 79 | 77 | 78 | 72 | 75 |

### Expert (10 bots)

| Seed | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 | 13 | 14 | 15 | 16 | 17 | 18 | 19 | 20 |
|------|---|---|---|---|---|---|---|---|---|----|----|----|----|----|----|----|----|----|----|----|
| Score | 41 | 35 | 36 | 67 | 52 | 46 | 55 | 56 | 32 | 54 | 45 | 14 | 75 | 40 | 41 | 54 | 53 | 11 | 45 | 54 |

Outliers: seed 12 (14), seed 18 (11) — severe congestion or layout issue.

## Timing Profile

| Difficulty | Avg decide_actions | Max decide_actions | P99 |
|------------|-------------------|-------------------|-----|
| Easy       | 0.035ms           | 1.07ms            | 0.12ms |
| Medium     | ~0.17ms           | ~2ms              | ~0.5ms |
| Hard       | ~0.37ms           | ~5ms              | ~1ms   |
| Expert     | ~0.94ms           | ~10ms             | ~3ms   |

All well within the 2s server limit.

## Test Suite

137 tests passing:
- 130 existing (unit, integration, regression, simulator)
- 7 new multi-bot collision edge cases (T6)

## Architecture (post-refactor)

| Module | Lines | Responsibility |
|--------|-------|---------------|
| round_planner.py | 386 | Orchestrator, step dispatch, needs computation |
| pickup.py | 321 | Active pickup, preview pre-pick, TSP routing |
| assignment.py | 228 | Bot-to-item assignment, preview bot selection |
| movement.py | 117 | BFS, collision avoidance, action emission |
| delivery.py | 111 | Delivery timing, end-game estimation |
| idle.py | 73 | Dropoff clearing, idle positioning |

## Known Issues

- Medium seeds 8, 15 score significantly below average (possible deadlock)
- Expert seeds 12, 18 score critically low (11-14) — severe congestion
- Expert idle time estimated 40-50% for many bots
- Simulator maps don't perfectly match live server (wall placement differs)
