# 2000+ Points Plan

## Current vs. Target

| Difficulty | Us (best) | #1 Maked | Target | Gain |
|------------|-----------|----------|--------|------|
| Easy       | 133       | 121      | 145    | +12  |
| Medium     | 153       | 205      | 240    | +87  |
| Hard       | 140       | 240      | 330    | +190 |
| Expert     | 119       | 341      | 400    | +281 |
| Nightmare  | 331       | 1250     | 1200   | +869 |
| **Total**  | **876**   | **2157** | **2315** | **+1439** |

The competitor is not tuning better — they use a fundamentally different strategy on large-bot maps.

---

## Root Cause: The Wave Delivery Gap

The #1 team's Nightmare score of 1250 (vs our 331) is the decisive gap. With 20 bots and the cascade delivery mechanic, a **double-batch wave strategy** can complete 2 orders per ~15-round cycle:

1. **Split**: 10 bots → active order items; 10 bots → preview order items (simultaneously)
2. **Fan out**: all 20 bots pick assigned items in parallel (~10–12 rounds)
3. **Converge**: when `wave_on_shelves == 0`, all 20 rush to drop-off together
4. **Cascade**: batch A's delivery completes order N; cascade immediately processes batch B's items against order N+1 — order N+1 completes in the same drop-off session
5. **Restart**: new active + preview assigned immediately; next wave begins

Result: **2 orders per 15 rounds** = 40 orders × 10 pts avg = 400 pts base.
With speculative triple-batch (6 bots pre-load order N+2): 1000–1200 pts.

Our current architecture processes one order at a time — preview is only "spare slot" opportunistic. This is a structural ceiling, not a tuning problem.

---

## Phase 1: Quick Wins (~+80 pts, 2–3 days)

### P1.1 — Wire `_should_deliver_early()` for small teams (+25 pts)
- **File**: `grocery_bot/planner/steps.py`
- `_step_early_delivery` guard is currently `4 <= num_bots < 8` — enable for all `num_bots < PREDICTION_TEAM_MIN`
- Fix the 34-round first-order delay on Medium
- **Impact**: +10 Medium, +10 Hard, +5 Expert

### P1.2 — Lower non-active clear threshold for medium teams (+15 pts)
- **File**: `grocery_bot/team_config.py`
- `nonactive_clear_min_inv()` returns `MAX_INVENTORY (3)` for 4–7 bot teams
- Bots hold 2 useless items for 40+ rounds waiting for a 3rd. Lower to `2`
- **Impact**: +10 Hard, +5 Medium

### P1.3 — Per-bot `_spare_slots` awareness (+23 pts)
- **File**: `grocery_bot/planner/pickup.py`
- `_spare_slots` reserves globally — unassigned bots can't preview-pick when other bots cover all active items
- Fix: `reserve = min(active_on_shelves, my_assigned_count)` per bot
- **Impact**: +8 Medium, +5 Hard, +10 Expert

### P1.4 — Oscillation suppression for Expert (+15 pts)
- **File**: `grocery_bot/planner/idle.py`
- Scale `IDLE_STAY_IMPROVEMENT_THRESHOLD` by team size
- Extend `_would_oscillate` to track last 3 positions (not just 2)
- **Impact**: +15 Expert

---

## Phase 2: Wave Foundation (~+500 pts, 4–6 days)

### W1 — Wave needs computation
- **File**: `grocery_bot/planner/round_planner.py`
- Add `wave_needed`, `wave_net`, `wave_on_shelves` to `_compute_needs()`
- `wave_needed = active_needed ∪ preview_needed`
- `wave_on_shelves = active_on_shelves + preview_items_remaining_on_shelves`
- Add `self.wave_mode = self.cfg.use_wave_mode and self.preview is not None`
- Add `use_wave_mode: bool` to `TeamConfig` (enabled for `num_bots >= 3`)
- New constants: `WAVE_MODE_MIN_BOTS = 3`, `WAVE_SYNC_THRESHOLD = 3`

### W2 — Batch A / Batch B assignment split
- **File**: `grocery_bot/planner/assignment.py`
- When `wave_mode`: split bots proportionally between active items (batch A) and preview items (batch B)
- `n_a = round(n_bots * active_items / wave_items)`
- Assign batch B bots to preview items as **primary mission** (not spare slots)
- Store `self.batch_b_bots: set[int]` in round state

### W3 — Protect batch B inventory from clearing
- **File**: `grocery_bot/planner/steps.py`
- `_step_clear_nonactive_inventory`: skip if `ctx.bid in self.batch_b_bots`
- `_step_idle_nonactive_deliver`: same exception
- Batch B's preview items are their mission, not waste

### W4 — Wave rush trigger
- **File**: `grocery_bot/planner/steps.py`
- Modify `_step_rush_deliver`: trigger when `wave_on_shelves == 0` (not just `active_on_shelves == 0`)
- Add `_step_wave_batch_b_rush`: batch B bots stage near drop-off when their preview items are all picked, even if `active_on_shelves > 0`

### W5 — Remove delivery throttling in wave mode
- **File**: `grocery_bot/planner/coordination.py`
- When `wave_on_shelves == 0`, set effective `max_concurrent_deliverers = num_bots`
- All bots admitted to delivery queue simultaneously
- Physical geometry of drop-off limits actual throughput naturally; cascade fires per bot's `drop_off` action in bot-id order

---

## Phase 3: Wave Optimization (~+200 pts, 2–4 days)

### W6 — Wave synchronization window (+30 pts)
- **File**: `grocery_bot/planner/steps.py`
- New step `_step_wave_sync_wait`: when `active_on_shelves == 0` but `wave_on_shelves <= WAVE_SYNC_THRESHOLD`, batch A bots stage at nearest approach cell instead of delivering immediately
- Ensures batch A and B arrive at drop-off together → cascade fires in 1–2 rounds instead of 5+
- **Impact**: +10–30 pts across wave-mode difficulties

### W7 — Triple-batch speculative for Nightmare (+150 pts)
- **File**: `grocery_bot/planner/speculative.py` (new)
- When `num_bots >= 15` and `wave_on_shelves == 0`: assign surplus empty-inventory bots as batch C
- Batch C picks any item type not in `wave_needed` (any item close to drop-off)
- With 21 types and 5-item orders, 24% hit rate per item — 18 speculative items → ~4 cascade items for order N+2
- **Impact**: +100–200 Nightmare

### W8 — Next-wave pipelining
- When `wave_on_shelves == 0` and a bot has empty inventory after delivering, immediately assign it to the next wave's items
- Overlap next wave pickup with current wave delivery
- Expected: shorten wave cycle by 2–4 rounds → +5–10% Nightmare throughput

---

## Phase 4: Per-Difficulty Polish (~+30 pts, 1–2 days)

| Task | Change | Impact |
|------|--------|--------|
| Easy route tables | Validate all 4-type order combinations covered | +10–12 |
| Expert last-slot | Ensure every bot loads a preview item in 3rd slot before delivering | +15–20 |
| Nightmare tail bots | Start next-wave pickup before current delivery finishes | +30–50 |

---

## Critical Files

| File | Changes Needed |
|------|---------------|
| `grocery_bot/planner/round_planner.py` | Add `wave_needed`, `wave_on_shelves`, `batch_b_bots` to `_compute_needs()` |
| `grocery_bot/planner/assignment.py` | Split assignment into batch A (active) + batch B (preview as primary) |
| `grocery_bot/planner/steps.py` | Wave rush trigger, batch B protection, T59 early delivery, T60 threshold |
| `grocery_bot/planner/coordination.py` | Remove concurrent deliverer cap in wave mode |
| `grocery_bot/team_config.py` | Add `use_wave_mode` flag, fix P1.2 threshold |
| `grocery_bot/constants.py` | `WAVE_MODE_MIN_BOTS`, `WAVE_SYNC_THRESHOLD` |

---

## Why the Cascade Works at Scale

The physics engine's `_do_dropoff` loop iterates `while changed and active_order_idx < len(orders)`. When bot 0 delivers and order N completes, the server advances to order N+1 immediately. Bot 1's `drop_off` action in the **same round** is checked against order N+1. With 20 bots delivering simultaneously, each bot's action can cascade to the next order — all within one round, with **zero extra movement**.

The key: 20 bots × 3 items = 60 items in one delivery wave. With 5-item orders, that's 12 orders' worth of inventory potentially completing via cascade in a single round.

---

## Implementation Order

```
Week 1: P1.1 + P1.2 + P1.3 + P1.4  →  ~+80 pts  →  ~956 total
Week 2: W1 + W2 + W3               →  wave foundation
Week 3: W4 + W5                    →  wave firing + +300-400 pts  →  ~1300 total
Week 4: W6 + W7                    →  +200 pts  →  ~1500 total
Week 5: W8 + Phase 4               →  +100 pts  →  ~1600+ total
```

Benchmark after each phase using `python benchmark.py` against `maps/2026-03-10_*.json`.
