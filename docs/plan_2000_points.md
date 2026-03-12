# Plan: Reaching 2000 Points

## Current State (2026-03-12)

| Difficulty | Bots | Rounds | Score | Orders | Rounds/Order | Recorded Orders | Key Problem |
|------------|------|--------|-------|--------|--------------|-----------------|-------------|
| Easy       | 1    | 300    | 121   | 14     | 20.8         | 16/50           | Travel time (solo bot) |
| Medium     | 3    | 300    | 147   | 16     | 18.6         | 19/50           | Near ceiling already |
| Hard       | 5    | 300    | 109   | 12     | 22.8         | 15/50           | 16.9% waste, low delivery density |
| Expert     | 10   | 300    | 109   | 10     | 27.3         | 12/50           | 23.4% waste, full-inv waiting |
| Nightmare  | 20   | 500    | 317   | 31     | 15.9         | 38/500          | Idle bots, full-inv gridlock |
| **Total**  |      |        | **803** | **83** |            |                 |             |

**Target: 2000** (2.5x improvement needed)

**Focus: Hard / Expert / Nightmare only.** Easy (1-bot) and Medium (3-bot) are near ceiling. Ignore regressions on those maps — all optimization effort targets multi-bot setups (5/10/20 bots).

## Why 2000 is Achievable

The current bot plays **reactively** — it sees active + preview orders and assigns bots to pick
those items. With 10-20 bots but only 3-7 items per order, most bots sit idle. The oracle
(recorded order knowledge from past runs) is barely exploited — it's only used as a distance
tiebreaker in speculative pickup.

The key unlock is **pipelining**: while 2-3 bots deliver order N, other bots pre-pick items
for orders N+1, N+2, N+3. With full oracle knowledge, the moment order N completes, bots
already holding N+1's items can immediately deliver. This collapses rounds-per-order from
15-27 down toward the delivery-travel-time minimum (~5-8 rounds).

### Score Budget

| Difficulty | Current | Target | Orders Needed | Strategy |
|------------|---------|--------|---------------|----------|
| Easy       | 121     | 180    | 21            | Better TSP routing, fewer wasted moves |
| Medium     | 147     | 200    | 22            | Tighter 3-bot coordination |
| Hard       | 109     | 300    | 30+           | Oracle pipelining with 5 bots |
| Expert     | 109     | 400    | 35+           | Fix waste, activate idle bots |
| Nightmare  | 317     | 920    | 80+           | Oracle pipeline, activate tail bots |
| **Total**  | **803** | **2000** |             |                                |

---

## Phase 1: Fix Regressions and Low-Hanging Fruit

**Goal: 803 → 950** (~18% gain)

Today's scores regressed from March 11 (881). Before adding features, recover lost ground.

### 1.1 Investigate and Fix Score Regression

Hard dropped from 135→109, Expert from 125→109. The maps changed (daily), but the planner
should handle any map well. Check if uncommitted changes in `constants.py`, `round_planner.py`,
`speculative.py`, `team_config.py` caused regressions.

- Compare today's scores with and without uncommitted changes
- Run March 11 maps with current code to isolate map-vs-code effects
- Fix any parameter drift

### 1.2 Reduce Waste Rate (Hard: 16.9%, Expert: 23.4%)

Bots pick items not needed for the active order, clogging their 3-slot inventory. This is the
single biggest performance killer on multi-bot maps.

**Fix**: Before picking any item speculatively, check if it matches:
1. Active order (always pick)
2. Preview order (pick if high confidence)
3. Skip otherwise — keep slots free

**Files**: `grocery_bot/planner/speculative.py`, `grocery_bot/planner/pickup.py`

### 1.3 Reduce Full-Inventory Waiting (Expert: 21.5%, Nightmare: 220 bot-rounds)

Bots hold 3 non-active items and can't pick active-order items. They wait for orders to cycle.

**Fix**: If a bot has full inventory and no items match the active order, it should deliver
what it can or move toward dropoff preemptively.

**Files**: `grocery_bot/planner/delivery.py`, `grocery_bot/planner/idle.py`

### 1.4 Faster Opening Round

First order consistently takes 2x the average (45-58 rounds). Opening dispersal is slow.

**Fix**: On round 0, assign bots directly to active-order items via Hungarian assignment
instead of generic dispersal.

**Files**: `grocery_bot/planner/spawn.py`

---

## Phase 2: Oracle Pipelining (The Big Unlock)

**Goal: 950 → 1400** (~47% gain)

This is the highest-ROI phase. With oracle knowledge, idle bots pre-pick items for future
orders, so delivery is near-instant when orders activate.

### 2.1 Oracle-Targeted Speculative Pickup

Currently, speculative pickup (step 18) picks the closest item of any type, with oracle as
a tiebreaker. Change to explicit oracle targeting:

- If oracle knows order N+2, idle bots **prioritize** items needed for N+2
- If oracle knows N+3, N+4, rank items by how soon they'll be needed
- Only fall back to generic closest-item when no oracle items are reachable

**Files**: `grocery_bot/planner/speculative.py`

### 2.2 Oracle Pre-Pick Step (New Planner Step)

Add `_step_oracle_prepick` between preview prepick (step 17) and speculative pickup (step 18):

- For each unassigned bot with spare inventory slots
- Look at oracle orders N+2..N+K (beyond preview)
- Find items needed for earliest future order not already being picked
- Assign bot to pick those items via TSP route
- **Guard**: only activate if >=4 recorded orders known (confidence threshold)

**Files**: `grocery_bot/planner/steps.py`, `grocery_bot/planner/round_planner.py`

### 2.3 Oracle-Aware Delivery Timing

With oracle knowledge, we can make smarter delivery decisions:

- If I deliver now and complete the order, what's the next order? Can I pre-pick on the way back?
- If the bot has 2+ active-order items and is closer to dropoff than to next pickup, deliver now
- Don't wait for full inventory if partial delivery + pre-pick is faster

**Files**: `grocery_bot/planner/delivery.py`

### 2.4 Inventory Slot Reservation

Prevent bots from filling inventory with items that won't be needed soon:

- Before picking an item, check if it appears in any of the next 3 oracle-known orders
- If not, skip it — keep inventory slots free for items that WILL be needed
- Exception: always pick active/preview order items

**Files**: `grocery_bot/planner/inventory.py`

---

## Phase 3: Bot Utilization (Expert + Nightmare)

**Goal: 1400 → 1800** (~29% gain)

Expert has 10 bots, Nightmare has 20. Most are idle. Oracle pipelining gives them work, but
they also need coordination to avoid stepping on each other.

### 3.1 Role-Based Bot Assignment

Assign bots into roles based on team size and oracle knowledge:

| Role | Count | Job |
|------|-------|-----|
| Carriers | 2-3 | Pick + deliver active order |
| Preview pickers | 1-2 | Pre-pick preview order items |
| Oracle pickers | 2-5 | Pre-pick N+2..N+K order items |
| Runners | 1-2 | Pre-positioned near dropoff, ready to deliver |

Roles rotate as orders complete. The key insight: **runners** hold pre-picked items near
dropoff. When their order activates, they deliver in 1-2 rounds instead of 15-20.

**Files**: `grocery_bot/planner/coordination.py`, `grocery_bot/planner/assignment.py`

### 3.2 Activate Tail Bots (Nightmare)

Bots 13-19 (7 of 20) are severely underutilized. Bot 19 completed 0 trips in 500 rounds.

- Assign tail bots exclusively to future oracle orders (N+2, N+3, N+4)
- They pre-pick and pre-position near the nearest dropoff zone
- When their order activates, they deliver immediately

**Files**: `grocery_bot/planner/idle.py`, `grocery_bot/planner/coordination.py`

### 3.3 Reduce Oscillation (Expert: 632 events)

Bots oscillate when they have no clear target. Each oscillation wastes a round.

- Strengthen oscillation breaker — trigger after 3 rounds instead of 5
- Replace oscillation with oracle-targeted movement: move toward next needed item
- If no oracle target, move toward map center (better average position)

**Files**: `grocery_bot/planner/movement.py`, `grocery_bot/constants.py`

### 3.4 Multi-Dropoff Exploitation (Nightmare)

Nightmare has 3 dropoff zones but bots currently all queue at the nearest one.

- Assign delivery bots to different dropoff zones to reduce congestion
- Route pre-positioned runners to the closest zone to their current position

**Files**: `grocery_bot/game_state/dropoff.py`, `grocery_bot/planner/delivery.py`

---

## Phase 4: Seed the Oracle (Live Server Runs)

**Goal: 1800 → 2000+** (final push via deeper oracle knowledge)

Oracle knowledge is the multiplier for all other improvements. More known orders = more
pipelining = faster completion = more orders discovered. This is the improve loop.

### 4.1 Run Live Server Repeatedly

Each run records new orders. With improved code from Phases 1-3, each run completes more
orders, discovering more of the sequence.

| Run | Est. Orders Known | Est. Score | Key Gain |
|-----|-------------------|------------|----------|
| Current | 16/19/15/12/38 | 803 | Baseline |
| After Phase 1 | same | 950 | Less waste, faster opening |
| Run 2 (with Phase 2 code) | 20/22/18/15/50 | 1100 | Oracle pipelining kicks in |
| After Phase 3 | same | 1400 | Full bot utilization |
| Run 3 | 25/28/22/20/70 | 1600 | Deeper oracle knowledge |
| Run 4 | 30/35/28/25/90 | 1800 | Most orders known |
| Run 5+ | 35/40/30/30/100+ | 2000+ | Near-complete oracle |

### 4.2 Order Accumulation Strategy

- Run each difficulty 3-5 times per day after code improvements
- Each run should discover 2-5 new orders per map
- Target: 30+ orders per map (Easy/Med/Hard/Expert), 80+ for Nightmare
- The live server runs should be done after each phase of code changes

---

## Phase 5: Advanced Optimizations

**Goal: 2000 → 2200+** (stretch goals, only if needed)

### 5.1 Temporal BFS for Collision Avoidance

Current BFS ignores bot-bot collisions. On Nightmare with 20 bots, collisions waste rounds.
Temporal BFS plans paths that account for where other bots will be in future rounds.

**Files**: `grocery_bot/pathfinding.py`

### 5.2 Wave Delivery (Nightmare)

Instead of delivering items one order at a time, batch deliveries:
- 5 bots each carry 3 items for different orders
- They all deliver simultaneously at 3 dropoff zones
- Orders complete in rapid succession, unlocking new orders faster

### 5.3 Endgame Rush Optimization

In the last 30-50 rounds, switch to maximum-throughput mode:
- Only pick items for orders that can be completed in remaining rounds
- Prioritize partial deliveries (+1 per item) over order completion (+5 bonus)
- Pre-position all bots near dropoff for rapid final deliveries

---

## Execution Order

| Step | Phase | Change | Est. Impact | Files |
|------|-------|--------|-------------|-------|
| 1 | 1.1 | Fix regressions | +50 | constants.py, team_config.py |
| 2 | 1.2 | Reduce waste | +30 | speculative.py, pickup.py |
| 3 | 1.3 | Fix full-inv waiting | +30 | delivery.py, idle.py |
| 4 | 1.4 | Faster opening | +20 | spawn.py |
| 5 | 2.1 | Oracle speculative | +100 | speculative.py |
| 6 | 2.2 | Oracle pre-pick step | +100 | steps.py, round_planner.py |
| 7 | 4.1 | Live server runs | +100 | (no code) |
| 8 | 2.3 | Oracle delivery timing | +50 | delivery.py |
| 9 | 3.1 | Role-based assignment | +100 | coordination.py, assignment.py |
| 10 | 3.2 | Activate tail bots | +80 | idle.py, coordination.py |
| 11 | 4.1 | More live server runs | +100 | (no code) |
| 12 | 3.3 | Reduce oscillation | +30 | movement.py, constants.py |
| 13 | 3.4 | Multi-dropoff | +30 | dropoff.py, delivery.py |
| 14 | 2.4 | Inventory reservation | +30 | inventory.py |
| 15 | 4.1 | Final live server runs | +100 | (no code) |

**Total estimated gain: ~1050 points** (803 → ~1850, with stretch goals pushing to 2000+)

---

## Verification After Each Step

```bash
# Run tests
python -m pytest tests/ -q --tb=line -m "not slow" 2>&1; echo "EXIT_CODE=$?"

# Run benchmark with diagnostics
python benchmark.py --diagnostics -v

# Read results
cat docs/benchmark_results.md

# Check for regressions on specific difficulty
python benchmark.py --map maps/2026-03-12_30x18_20bot.json --diagnostics -v

# Analyze problems
python analyze_replay.py <log> --problems 2>&1 | tail -30

# Check bot utilization
python analyze_replay.py <log> --bot <id> 2>&1 | tail -20
```

## Critical Files

| File | Phase | Changes |
|------|-------|---------|
| `grocery_bot/planner/speculative.py` | 1.2, 2.1 | Waste reduction + oracle targeting |
| `grocery_bot/planner/steps.py` | 2.2 | New `_step_oracle_prepick` |
| `grocery_bot/planner/round_planner.py` | 2.2 | Wire new step into chain |
| `grocery_bot/planner/delivery.py` | 1.3, 2.3 | Earlier delivery + oracle timing |
| `grocery_bot/planner/coordination.py` | 3.1, 3.2 | Roles + tail bot activation |
| `grocery_bot/planner/idle.py` | 1.3, 3.2 | Oracle idle targets |
| `grocery_bot/planner/assignment.py` | 3.1 | Role-based assignment |
| `grocery_bot/planner/movement.py` | 3.3 | Oscillation reduction |
| `grocery_bot/planner/spawn.py` | 1.4 | Faster opening |
| `grocery_bot/planner/pickup.py` | 1.2 | Waste filtering |
| `grocery_bot/planner/inventory.py` | 2.4 | Slot reservation |
| `grocery_bot/game_state/dropoff.py` | 3.4 | Multi-zone routing |
| `grocery_bot/constants.py` | All | New thresholds |
