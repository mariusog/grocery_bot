"""Named constants for the Grocery Bot decision engine.

All magic numbers used across the codebase are centralized here
for readability and easy tuning.
"""

# ---------------------------------------------------------------------------
# Inventory and game limits
# ---------------------------------------------------------------------------
MAX_INVENTORY = 3  # max items a bot can carry at once
BOT_HISTORY_MAXLEN = 3  # rounds of position history per bot

# ---------------------------------------------------------------------------
# End-game thresholds
# ---------------------------------------------------------------------------
ENDGAME_ROUNDS_LEFT = 40  # rounds_left <= this triggers endgame mode

# ---------------------------------------------------------------------------
# Order completion thresholds
# ---------------------------------------------------------------------------
ORDER_NEARLY_COMPLETE_MAX = 2  # active_on_shelves <= this = "nearly complete"

# ---------------------------------------------------------------------------
# Pickup failure / blacklisting
# ---------------------------------------------------------------------------
PICKUP_FAIL_BLACKLIST_THRESHOLD = 3  # consecutive fails before blacklisting an item

# ---------------------------------------------------------------------------
# Bot team-size thresholds for strategy branching
# ---------------------------------------------------------------------------
SMALL_TEAM_MAX = 3  # len(bots) <= this for small-team logic
MEDIUM_TEAM_MIN = 5  # len(bots) >= this for medium-team logic
LARGE_TEAM_MIN = 6  # len(bots) >= this for large-team logic
PREDICTION_TEAM_MIN = 8  # len(bots) >= this to use predicted positions

# ---------------------------------------------------------------------------
# Blocking / collision avoidance
# ---------------------------------------------------------------------------
BLOCKING_RADIUS_LARGE_TEAM = 6  # Manhattan blocking radius for 5+ bots

# ---------------------------------------------------------------------------
# Delivery / dropoff proximity
# ---------------------------------------------------------------------------
DELIVER_WHEN_CLOSE_DIST = 3  # d_to_drop <= this triggers early delivery
DROPOFF_CLEAR_RADIUS = 3  # idle bots clear dropoff within this distance

# ---------------------------------------------------------------------------
# Idle positioning scoring weights
# ---------------------------------------------------------------------------
IDLE_DROPOFF_PENALTY_RADIUS = 3  # penalize idle bots within this dist of dropoff
IDLE_DROPOFF_PENALTY_FACTOR = 3  # weight: (radius+1 - dist) * factor
IDLE_BOT_PROXIMITY_RADIUS = 2  # penalize idle bots within this dist of each other
IDLE_BOT_PROXIMITY_FACTOR = 2  # weight: (radius+1 - dist) * factor
IDLE_TARGET_DISTANCE_WEIGHT = 0.5  # reward proximity to target position
IDLE_STAY_IMPROVEMENT_THRESHOLD = 0.5  # only move from idle spot if improvement >= this
IDLE_CORRIDOR_PENALTY = 4  # penalty for idle bots sitting in main corridor rows (large teams)

# ---------------------------------------------------------------------------
# Zone-based assignment penalties
# ---------------------------------------------------------------------------
ZONE_CROSS_PENALTY = 3  # penalty per zone difference in assignment scoring

# ---------------------------------------------------------------------------
# Detour / preview pickup
# ---------------------------------------------------------------------------
MAX_DETOUR_STEPS = 3  # default max detour to pick up an item en route
CASCADE_DETOUR_STEPS = 6  # max detour when picking cascade (preview) items

# ---------------------------------------------------------------------------
# Clustering weights
# ---------------------------------------------------------------------------
CLUSTER_DISTANCE_WEIGHT = 0.3  # weight for cluster centroid distance in scoring

# ---------------------------------------------------------------------------
# Non-active delivery limits (dropoff congestion control)
# ---------------------------------------------------------------------------
MAX_NONACTIVE_DELIVERERS = 1  # max bots delivering non-active inventory at once

# ---------------------------------------------------------------------------
# Corridor / idle spot computation
# ---------------------------------------------------------------------------
CORRIDOR_HEIGHT_THRESHOLD = 10  # grid heights > this get a second corridor row

# ---------------------------------------------------------------------------
# Hungarian algorithm threshold
# ---------------------------------------------------------------------------
HUNGARIAN_MAX_PAIRS = 100  # n_bots * n_items <= this uses Hungarian; else greedy

# ---------------------------------------------------------------------------
# Minimum inventory for non-active delivery
# ---------------------------------------------------------------------------
MIN_INV_FOR_NONACTIVE_DELIVERY = 2  # bots need >= this many items to deliver non-active

# ---------------------------------------------------------------------------
# Last-item priority boost (T16)
# ---------------------------------------------------------------------------
LAST_ITEM_BOOST_THRESHOLD = 2  # active_on_shelves <= this triggers boost
LAST_ITEM_COST_MULTIPLIER = 0.33  # cost multiplier (3x priority = 1/3 cost)

# ---------------------------------------------------------------------------
# Delivery queue / coordination (T15)
# ---------------------------------------------------------------------------
DELIVERY_QUEUE_TEAM_MIN = 4  # len(bots) >= this to use delivery queue
MAX_CONCURRENT_DELIVERERS = 2  # max bots navigating to dropoff at once (large teams)
TASK_COMMITMENT_ROUNDS = 5  # min rounds a bot stays committed to a task
