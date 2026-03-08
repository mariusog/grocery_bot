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
BLACKLIST_EXPIRY_ROUNDS = 15  # rounds before a blacklisted item is retried

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
BLOCKING_RADIUS_LARGE_TEAM = 4  # default Manhattan blocking radius for 5+ bots
BLOCKING_RADIUS_EXPERT = 5  # Manhattan blocking radius for 8-14 bot teams
BLOCKING_RADIUS_HUGE_TEAM = 3  # tighter radius for 15+ bot teams

# ---------------------------------------------------------------------------
# Delivery / dropoff proximity
# ---------------------------------------------------------------------------
DELIVER_WHEN_CLOSE_DIST = 3  # d_to_drop <= this triggers early delivery
DROPOFF_CLEAR_RADIUS = 3  # idle bots clear dropoff within this distance

# ---------------------------------------------------------------------------
# Idle positioning scoring weights
# ---------------------------------------------------------------------------
IDLE_DROPOFF_PENALTY_RADIUS = 2  # penalize idle bots within this dist of dropoff
IDLE_DROPOFF_PENALTY_FACTOR = 3  # weight: (radius+1 - dist) * factor
IDLE_BOT_PROXIMITY_RADIUS = 2  # penalize idle bots within this dist of each other
IDLE_BOT_PROXIMITY_FACTOR = 2  # weight: (radius+1 - dist) * factor
IDLE_TARGET_DISTANCE_WEIGHT = 0.5  # reward proximity to target position
IDLE_NO_TARGET_ATTRACT_MIN = 10  # disable target attraction for teams this large
IDLE_STAY_IMPROVEMENT_THRESHOLD = 0.5  # only move from idle spot if improvement >= this
IDLE_CORRIDOR_PENALTY = 4  # penalty for idle bots sitting in main corridor rows (large teams)
IDLE_PREVIEW_STAGE_WEIGHT_5BOT = 0.5  # dropoff bias for 5-bot preview carriers
IDLE_PREVIEW_STAGE_WEIGHT_10BOT = 0.4  # dropoff bias for 10-bot preview carriers

# ---------------------------------------------------------------------------
# Multi-drop-zone congestion weighting
# ---------------------------------------------------------------------------
ZONE_CONGESTION_WEIGHT = 1.0  # per-bot penalty when choosing nearest drop zone

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
HUNGARIAN_MAX_PAIRS = 200  # n_bots * n_items <= this uses Hungarian; else greedy

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

# ---------------------------------------------------------------------------
# Dropoff congestion management (game_state/dropoff.py)
# ---------------------------------------------------------------------------
DROPOFF_CONGESTION_RADIUS = 3  # adjacents within this BFS dist of dropoff
DROPOFF_WAIT_DISTANCE = 4  # wait cells sit at this BFS dist from dropoff
MAX_APPROACH_SLOTS = 2  # max bots allowed to approach dropoff simultaneously

# ---------------------------------------------------------------------------
# Distance / path caching (game_state/)
# ---------------------------------------------------------------------------
DIST_CACHE_MAX = 512  # max entries in dist_cache LRU
PATH_RECHECK_INTERVAL = 5  # rounds between path-cache validity rechecks

# ---------------------------------------------------------------------------
# BFS exploration limits (pathfinding.py)
# ---------------------------------------------------------------------------
BFS_MAX_CELLS = 2000  # max cells explored by standard BFS functions
TEMPORAL_BFS_MAX_CELLS = 4000  # max cells explored by temporal BFS

# ---------------------------------------------------------------------------
# Diagnostic thresholds (simulator/runner.py)
# ---------------------------------------------------------------------------
DIAG_LOW_SCORE = 50  # score < this flags LOW_SCORE
DIAG_HIGH_IDLE_PCT = 30  # idle% > this flags HIGH_IDLE
DIAG_HIGH_STUCK_PCT = 10  # stuck% > this flags HIGH_STUCK
DIAG_LONG_GAP = 40  # max_delivery_gap > this flags LONG_GAP
DIAG_OSCILLATION = 20  # oscillation_count > this flags OSCILLATING

# ---------------------------------------------------------------------------
# Speculative pickup (planner/speculative.py)
# ---------------------------------------------------------------------------
SPEC_MAX_TEAM_COPIES = 2  # skip item types already carried by >= this many bots

# ---------------------------------------------------------------------------
# Spawn dispersal (planner/spawn.py)
# ---------------------------------------------------------------------------
SPAWN_DISPERSAL_MAX_ROUNDS = 12  # only apply spawn dispersal in the opening
