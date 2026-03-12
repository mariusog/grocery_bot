# Hard Difficulty InvFull Fix Plan

## Problem Statement

On Hard (5 bots, 22x14), bots fill inventory with non-active (preview) items,
then wait 48+ rounds with full inventory before delivering. This delays active
order completion — first order takes R49 instead of ~R15-20.

**Evidence** (Hard diagnostic, seed 42):
- Score: 152 | Orders: 17 | InvFull waits: 93 | Waste: 63.7%
- Bot 4: picks pasta(R11), sugar(R13), flour(R15) → ALL non-active → waits 48 rounds
- Bot 3: picks pasta(R18), bread(R19), eggs(R21) → ALL non-active → waits 18 rounds
- Bot 0: picks yogurt(R2, active), bread(R4, PREVIEW), milk(R9, active) → preview delays active
- Active order needs [cheese, milk, salt, butter, yogurt] — 5 items for 5 bots
- First order completion: R49

## Root Cause Analysis

### Cause 1: `_step_opportunistic_preview` too permissive (step 6)

**File**: `grocery_bot/planner/steps.py:113-147`

Fires BEFORE `_step_active_pickup` (step 10). For 5-bot teams:
- Solo guard: `len(self.bots) == 1` → False (5 bots)
- Assignment guard: `len(self.bots) < SMALL_TEAM_MAX` → `5 < 3` → False
- Adjacent-active guard: only blocks if active item is ALSO adjacent

Result: bots freely pick adjacent preview items on route to active items.
Bot 0 picks bread (preview) at R4 between yogurt (R2) and milk (R9).

### Cause 2: `_step_preview_prepick` routes bots to distant preview (step 13)

**File**: `grocery_bot/planner/preview.py:17-74`

Pass 2 (walk to distant preview items) gate at line 46:
```python
if len(self.bots) < MEDIUM_TEAM_MIN and self.active_on_shelves > 0:
    return False  # Small teams: don't divert
```
`MEDIUM_TEAM_MIN = 5`, so `5 < 5` → False. The gate does NOT fire for 5-bot teams.

Max walkers: `max(2, 5 // 2) = 2` — allows 2 bots to walk toward distant preview.

Result: Bot 3 and Bot 4 walk to distant preview items, fill all 3 inventory slots
with non-active items, then have no room for active items.

### Cause 3: `_spare_slots` too generous for assigned bots

**File**: `grocery_bot/planner/round_planner.py:409-415`

```python
reserve = min(self.active_on_shelves, my_assigned)
```

Assigned bot with 1 assignment, 5 active on shelves:
- `reserve = min(5, 1) = 1`
- `spare = 3 - 0 - 1 = 2`

Bot can fill 2 of 3 inventory slots with preview items. Only 1 slot reserved.

### Cause 4: `_step_deliver_active` detour (step 11)

**File**: `grocery_bot/planner/steps.py:226-232`

When carrying active items to delivery, bots detour for preview items:
```python
spare = self._spare_slots(ctx.inv, ctx.bid)
if self.preview and spare > 0 and not self.order_nearly_complete:
    item, cell = self._find_detour_item(ctx.pos, self.net_preview)
```

When active_on_shelves is high, this delays delivery and lets other bots pick
those same active items — wasting turns.

## Key Insight

**When `active_on_shelves >= num_bots`, every bot has active work to do.**
No bot should waste inventory or turns on preview items in this state.

When `active_on_shelves < num_bots`, surplus bots exist and CAN usefully
pick preview items for cascade delivery.

## Proposed Fixes

### Fix A: Extend opportunistic preview guard (Cause 1)

**File**: `grocery_bot/planner/steps.py`

Replace the `< SMALL_TEAM_MAX` assignment guard with an active-saturation condition:

```python
# Current:
if (
    len(self.bots) < SMALL_TEAM_MAX
    and self.bot_assignments.get(ctx.bid)
):
    return False

# Proposed:
if (
    self.bot_assignments.get(ctx.bid)
    and self.active_on_shelves >= len(self.bots)
):
    return False
```

When there's enough active work for all bots (`active >= bots`), assigned bots
skip preview. On large teams (20 bots, 5 active → `5 >= 20` False), preview
picking is preserved.

**Risk**: Low. Only blocks when there's active work for everyone.

### Fix B: Gate preview prepick walking for 5-bot teams (Cause 2)

**File**: `grocery_bot/planner/preview.py`

Change Pass 2 gate from `<` to `<=`:

```python
# Current:
if len(self.bots) < MEDIUM_TEAM_MIN and self.active_on_shelves > 0:
    return False

# Proposed:
if len(self.bots) <= MEDIUM_TEAM_MIN and self.active_on_shelves > 0:
    return False
```

Prevents 5-bot teams from walking to distant preview items when active items
exist. Adjacent preview pickup (Pass 1) is unaffected.

**Risk**: Medium. May lose some preview pre-picking on 5-bot teams when
active items are almost done (e.g., active_on_shelves = 1).

**Alternative** (lower risk): Use active-saturation condition:
```python
if (
    len(self.bots) < MEDIUM_TEAM_MIN
    or self.active_on_shelves >= len(self.bots)
) and self.active_on_shelves > 0:
    return False
```

This preserves walking on 5-bot teams when most active items are picked.

### Fix C: Tighten `_spare_slots` for assigned bots in active-saturated state (Cause 3)

**File**: `grocery_bot/planner/round_planner.py`

When active work saturates the team, assigned bots reserve all free slots:

```python
# Current:
my_assigned = len(self.bot_assignments.get(bid, []))
reserve = min(self.active_on_shelves, my_assigned)

# Proposed:
my_assigned = len(self.bot_assignments.get(bid, []))
if my_assigned > 0 and self.active_on_shelves >= len(self.bots):
    reserve = min(self.active_on_shelves, MAX_INVENTORY - len(inv))
else:
    reserve = min(self.active_on_shelves, my_assigned)
```

When `active_on_shelves >= num_bots`, assigned bots reserve ALL slots for active.
Otherwise, current behavior (reserve only assigned count).

**Risk**: Medium. Affects all steps that use `_spare_slots`. May block useful
cascade-picking. But only fires when team is fully saturated with active work.

### Fix D: Skip delivery detour when active-saturated (Cause 4)

**File**: `grocery_bot/planner/steps.py`

Add active-saturation check to detour logic in `_step_deliver_active`:

```python
# Current:
if self.preview and spare > 0 and not self.order_nearly_complete:

# Proposed:
if (
    self.preview and spare > 0
    and not self.order_nearly_complete
    and self.active_on_shelves < len(self.bots)
):
```

When active-saturated, bots rush to deliver active items instead of detouring.

**Risk**: Low. Only skips detour when there's enough active work for all bots.

## Implementation Order (TDD)

### Phase 1: Fix A + Fix B (targeted guards, least invasive)

1. Write tests for the expected behavior changes
2. Implement Fix A (opportunistic preview guard)
3. Implement Fix B (preview prepick walking gate)
4. Run `pytest -q --tb=line -m "not slow"`
5. Benchmark Easy → verify no regression
6. Benchmark Medium → verify no regression
7. Benchmark Hard → expect improvement in InvFull waits

### Phase 2: Fix D (delivery detour gate)

1. Write test for delivery detour skipping
2. Implement Fix D
3. Run pytest + Easy/Medium/Hard benchmarks

### Phase 3: Fix C (spare_slots tightening) — only if Phase 1-2 insufficient

Fix C is the most invasive (affects all spare_slots consumers). Only attempt
if Phase 1-2 don't sufficiently reduce InvFull waits.

1. Write test for spare_slots behavior change
2. Implement Fix C
3. Run full benchmark suite

## Success Criteria

- Hard InvFull waits: 93 → <50 (>45% reduction)
- Hard waste: 63.7% → <50%
- Hard first order: R49 → <R30
- Easy/Medium: no regression (±5 acceptable for noise)
- Expert/Nightmare: accept short-term regression if Hard improves significantly

## Previous Attempts (what NOT to do)

| Fix | Result | Why it failed |
|-----|--------|---------------|
| Broad guard (all bots, all teams) | -190 | Blocked ALL preview → destroyed cascade |
| Assignment guard ≤3 bots | -20 on Medium | All 3 bots assigned → no preview at all |
| `_spare_slots` reserve=1 unassigned | -143 | Blocked useful preview in prepick |
| Dropoff-distance in assignment | -50 on Medium | Non-uniform Hungarian bias |

## Key Difference from Previous Attempts

Previous fixes used static thresholds (team size < N). This plan uses
**active saturation** (`active_on_shelves >= len(self.bots)`), which
dynamically adapts:

- Game start (5 active, 5 bots): fully saturated → focus active
- Mid-order (2 active, 5 bots): not saturated → allow preview
- Between orders (0 active): not saturated → full preview

This avoids the "all or nothing" problem that caused previous regressions.
