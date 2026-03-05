# Grocery Bot Optimization Plan

## Current Baseline
- **Easy map**: 96 points (41 items, 11 orders) in 300 rounds
- ~27 rounds per order → target: **<20 rounds per order**

## Analysis of Lost Rounds

The bot wastes rounds in three ways:
1. **Suboptimal routing** — greedy nearest-item picks bad sequences
2. **Redundant trips** — delivers 1 item, walks back for more, delivers again
3. **No pipelining** — bot idles between order completion and next pickup

---

## Phase 1: Distance Matrix & Route Planning (Biggest Impact)

### 1.1 Precompute Distance Matrix
Cache BFS distances between all key positions (item locations, dropoff, spawn) on round 0. The map is static within a game — never recompute pathfinding from scratch.

**Impact**: Eliminates ~90% of BFS calls. Turns O(V) per decision into O(1) lookup.

### 1.2 TSP-Optimal Pickup Ordering
Each order has 3-6 items. Finding the shortest pickup route is a tiny TSP (3-6 nodes + dropoff). With ≤7 nodes, brute-force all permutations (7! = 5040). Pick the sequence that minimizes total travel: `bot → item1 → item2 → ... → dropoff`.

**Impact**: Cuts ~5-8 rounds per order on easy. Could mean 2-3 extra orders completed.

### 1.3 Combined Pickup-Delivery Planning
Don't always pick up ALL items before delivering. If the bot passes the dropoff mid-route, consider partial delivery + continue picking. Evaluate: `full-route-then-deliver` vs `interleaved-delivery` and pick shorter.

---

## Phase 2: Preview Order Pipelining

### 2.1 Speculative Pre-Picking
The preview order is fully visible. While heading to deliver the last item(s) of the active order, calculate if any preview items are "on the way" or close to the delivery path. Pick them up opportunistically.

### 2.2 Dedicated Preview Bot (Multi-Bot)
On Medium+ maps, assign 1+ bots to exclusively pre-pick preview order items while others finish the active order. When the active order completes, the preview bot may already have items ready → instant delivery.

### 2.3 Delivery Cascade Awareness
When active order completes, items for the new active order that are already in bot inventories auto-deliver on next dropoff. Plan for this: if a bot has preview items and is near dropoff, have it position there for instant cascade.

---

## Phase 3: Multi-Bot Coordination (Medium/Hard/Expert)

### 3.1 Item Assignment via Hungarian Algorithm
Assign items to bots by minimizing total travel distance. Build a cost matrix: `cost[bot][item] = BFS distance from bot to item's adjacent cell`. Solve assignment optimally with the Hungarian algorithm (or greedy for speed given the 2s timeout).

### 3.2 Anti-Collision Pathfinding
Current approach treats other bots as static walls — this causes deadlocks in narrow aisles. Instead:
- **Priority-based movement**: Lower-ID bots move first (matches game rules). Higher-ID bots plan around predicted positions of lower-ID bots.
- **Wait-and-yield**: If a bot detects it's blocking another's optimal path and has no urgent task, it yields.
- **One-way aisle convention**: In tight aisles, bots traveling in opposite directions cause gridlock. Assign preferred directions to aisles.

### 3.3 Zone Assignment
Divide the store into zones (one per aisle pair). Assign bots to zones to minimize cross-traffic. Bots pick items in their zone first, only cross zones for items not available locally.

### 3.4 Pickup/Delivery Specialization
For Expert (10 bots), consider roles:
- **Pickers** (7-8 bots): grab items, pass them via intermediate positions
- **Runners** (2-3 bots): shuttle between aisles and dropoff
This reduces congestion at the dropoff.

---

## Phase 4: Advanced Scoring Optimization

### 4.1 Order Completion Priority
+5 bonus per order is ~60% of total score. If an order needs 1 more item, that item is worth 6 points (1 + 5 bonus). Prioritize "almost complete" orders — reassign bots from low-value pickups to high-value completion tasks.

### 4.2 Item Proximity Clustering
When choosing between two needed items of the same type, always pick the one closer to other needed items (reduces total route length). Use center-of-mass of remaining needed items as a tiebreaker.

### 4.3 End-Game Strategy
In the last ~30 rounds, switch from "complete orders" to "maximize items delivered":
- If current order can't be completed in remaining rounds, still deliver partial items (+1 each)
- Don't waste rounds on distant items if closer non-order items exist
- Calculate: `rounds_remaining vs rounds_to_complete_order` to decide strategy

### 4.4 Dropoff Timing
Deliver partial items if:
- It completes the order (triggers +5 bonus and unlocks next order)
- Bot is passing dropoff anyway en route to next item
- Inventory is full and blocking needed pickups

Don't deliver partial items if:
- It requires a detour and won't complete the order
- Bot has empty inventory slots and more items are nearby

---

## Phase 5: Implementation Architecture

### 5.1 Game State Manager
Centralized state tracker that maintains:
- Distance matrix (computed once on round 0)
- Item assignments per bot
- Bot targets and planned paths
- Order progress tracking

### 5.2 Round Budget
Always know: `rounds_remaining`, `estimated_rounds_for_current_order`, `expected_orders_completable`. Use this to make strategic decisions (e.g., skip an order if it's too expensive).

### 5.3 Determinism Exploitation
Games are deterministic per day. Run the game once to observe order sequences, then optimize routes on subsequent runs. Not cheating — the docs explicitly state this property.

---

## Priority Order

| Priority | Phase | Expected Gain | Effort |
|----------|-------|---------------|--------|
| 1 | 1.1 Distance matrix | +15% speed | Low |
| 2 | 1.2 TSP routing | +20% score | Medium |
| 3 | 2.1 Preview pipelining | +15% score | Medium |
| 4 | 3.1 Bot assignment | Required for Medium+ | Medium |
| 5 | 4.1 Order completion priority | +10% score | Low |
| 6 | 3.2 Anti-collision | Required for Hard+ | High |
| 7 | 4.3 End-game strategy | +5% score | Low |
| 8 | 3.3 Zone assignment | Polish for Expert | Medium |

**Target**: Easy 150+, Medium 200+, Hard 250+, Expert 300+
