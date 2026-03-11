# Daily Map Improvement Plan (2026-03-11)

## Current Live Scores

| Difficulty | Score | Orders | Rounds/Order | Items |
|-----------|-------|--------|-------------|-------|
| Easy | 133 | 16 | 18.8 | 53 |
| Medium | 173 | 19 | 15.8 | 78 |
| Hard | 115 | 12 | 25.0 | 55 |
| Expert | 114 | 11 | 27.3 | 59 |
| Nightmare | 326 | 30 | 16.7 | 176 |
| **Total** | **861** | | | |

## Diagnosis: Medium (3 bots, 16x12, 300 rounds)

### M1 — Scoring gaps from long delivery walks (113 wasted rounds)
Five gaps of 20-26 rounds each where no points are scored. Root cause: all 3 bots are
either walking to the dropoff or walking to distant items simultaneously. No bot is
actively near items while others deliver.

**Evidence**: R33-R59 gap — B0 walks 8 rounds to deliver [milk,yogurt,yogurt], B2 walks
8 rounds to deliver [eggs,pasta,cheese], B1 has [pasta,pasta,pasta] and oscillates near
the dropoff waiting for its turn. All 3 bots converge on dropoff simultaneously.

**Impact**: ~113 rounds with no scoring = ~38% of the game.

### M2 — Oscillation near dropoff (R156, 6-7 rounds)
Bots 0 and 2 oscillate at R156 for 6-7 rounds. B0 @(4,9) moves left, B2 @(4,3) moves
down — they're heading to dropoff but getting bounced. B1 is the active deliverer at
(1,5) heading down with [cheese,butter,butter].

**Root cause**: B0 has [yogurt] (preview) and is being routed by `_step_preview_prepick`
away then pulled back by `_step_shadow_deliver`, creating oscillation.

### M3 — Late-game oscillation (R284-298, 14 rounds)
B0 oscillates between (4,9)-(3,9)-(4,9) for 14 rounds at the end. Score stuck at 165
from R282. B2 carries [butter,butter,cheese] heading to dropoff = 8 points on the last
round. B0 has [milk] and oscillates instead of delivering or pre-picking.

**Impact**: Lost ~1 order (8+ points) from endgame wasted motion.

---

## Diagnosis: Hard (5 bots, 22x14, 300 rounds)

### H1 — Full inventory waits (24+11+9+5 = 49 bot-rounds)
Bot 4 waits 24 rounds with full inventory [oats,butter,rice] — none are active items.
The `_step_clear_nonactive_inventory` throttle (`max_nonactive_deliverers`) limits to 1
bot delivering non-active items. With 5 bots, multiple bots clog up waiting.

Bot 2 waits 11 rounds, Bot 3 waits 9 rounds, Bot 0 waits 5 rounds — all with full
inventories of non-active items blocking active item pickup.

### H2 — Multi-bot oscillation storms (R210: 12+11 rounds, R245+R255: 7+7 rounds)
At R210, Bots 0 and 3 oscillate for 11-12 rounds simultaneously. At R245 and R255,
Bot 1 oscillates for 7 rounds each time.

**Root cause**: When `active_on_shelves` is low (1-2 items), multiple bots compete for
the same item. They route toward it, find another bot closer, re-route away, then
re-route back next round.

### H3 — Dropoff congestion with 5 bots (R38-R46)
Bot 4 picks up 3 items by R28, then spends R29-R46 (17 rounds!) navigating toward the
dropoff through congestion. Bot 3 has a similar pattern — picks up by R28, doesn't
deliver until R57+. The dropoff (1,12) is in a corner, creating a single-lane bottleneck.

### H4 — Endgame failure (R298-299)
At R299: B2 has [eggs,eggs,eggs], B3 has [pasta,cream], B4 has [oats,flour]. Active
order needs [eggs:1]. B2 is at (1,7) heading to dropoff at (1,12) = 5 rounds away.
Game ends before delivery. Better endgame detection could have prioritized B2's rush.

---

## Improvement Tasks (Priority Order)

### P1: Raise non-active clearing throttle for medium teams
**Target**: Medium M1, Hard H1 | **Est. impact**: +10-15 points each

The `max_nonactive_deliverers` cap is too low for 3-5 bot teams. When all bots have
non-active inventory, only 1 can deliver while the rest wait idle. For 3-bot teams,
allow 2 simultaneous non-active deliverers. For 5-bot teams, allow 2-3.

**Files**: `grocery_bot/team_config.py` (adjust `max_nonactive_deliverers` per team size)

### P2: Fix oscillation when active_on_shelves is low
**Target**: Medium M2/M3, Hard H2 | **Est. impact**: +8-12 points each

When `active_on_shelves <= 2`, multiple bots route toward the same remaining items and
oscillate. Fix: when `active_on_shelves` is low and the bot has NO assignment for the
remaining items, it should prefer delivering or pre-picking preview items instead of
oscillating toward an item another bot is closer to.

**Files**: `grocery_bot/planner/steps.py` (add low-active-on-shelves guard to
`_step_active_pickup` or add a new step), `grocery_bot/planner/pickup.py`

### P3: Stagger delivery timing to maintain continuous scoring
**Target**: Medium M1 | **Est. impact**: +5-8 points

All 3 bots converge on the dropoff simultaneously, creating 20-26 round gaps. If one
bot delivers while others pick, scoring is continuous. The `_step_deliver_active` detour
logic exists but doesn't trigger often enough for 3-bot teams.

**Files**: `grocery_bot/planner/steps.py` (`_step_deliver_active`),
`grocery_bot/planner/delivery.py`

### P4: Improve endgame rush for last-order completion
**Target**: Medium M3, Hard H4 | **Est. impact**: +5-8 points each

At R282+ (Medium) and R295+ (Hard), bots oscillate or pick up unnecessary items instead
of rushing the final delivery. The `_step_endgame` fires at `ENDGAME_ROUNDS_LEFT` but
may not be aggressive enough about dropping everything to deliver.

**Files**: `grocery_bot/planner/steps.py` (`_step_endgame`),
`grocery_bot/constants.py` (`ENDGAME_ROUNDS_LEFT`)

### P5: Reduce dropoff congestion for corner dropoffs
**Target**: Hard H3 | **Est. impact**: +3-5 points

Corner dropoffs (1,12) have only 2 approach cells. With 5 bots, this creates a
permanent bottleneck. Better spread of delivery timing (P3) partially helps, but the
`_try_clear_dropoff` radius may need to be more aggressive at evicting idle bots from
the approach corridor.

**Files**: `grocery_bot/planner/idle.py` (`_try_clear_dropoff`),
`grocery_bot/constants.py` (`DROPOFF_CLEAR_RADIUS`)

---

## Scoring Targets

| Difficulty | Current | Target | Delta | Key Tasks |
|-----------|---------|--------|-------|-----------|
| Medium | 173 | 190+ | +17 | P1, P2, P3, P4 |
| Hard | 115 | 135+ | +20 | P1, P2, P4, P5 |
| Expert | 114 | 125+ | +11 | Benefits from P1, P2 |
| Nightmare | 326 | 340+ | +14 | Benefits from P1 |
| **Total** | **861** | **923+** | **+62** | |

## Implementation Order

1. **P1** first — simplest change (config tuning), biggest bang for buck
2. **P2** next — fixes the most common problem across both Medium and Hard
3. **P4** then — endgame points are "free" once detected properly
4. **P3** and **P5** last — more architectural, may need careful testing

## Verification Protocol

After each change:
1. `python -m pytest tests/ -q --tb=line -m "not slow" 2>&1 | tail -20`
2. `python benchmark.py --diagnostics` (replay maps)
3. `cat docs/benchmark_results.md` — check no regression
4. `python analyze_replay.py <medium-log> --problems` — verify problem count reduced
5. `python analyze_replay.py <hard-log> --problems` — verify problem count reduced
