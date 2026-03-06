"""Pure pathfinding functions and movement helpers."""

from collections import deque
from typing import Optional

DIRECTIONS: list[tuple[int, int]] = [(0, -1), (0, 1), (-1, 0), (1, 0)]

def bfs_all(
    source: tuple[int, int],
    blocked: set[tuple[int, int]],
) -> dict[tuple[int, int], int]:
    """BFS from source to ALL reachable cells. Returns {pos: distance}.

    Args:
        source: (x, y) starting position.
        blocked: set of (x, y) positions that cannot be entered.

    Returns:
        dict mapping (x, y) -> int distance from source.
    """
    distances: dict[tuple[int, int], int] = {source: 0}
    queue = deque([source])
    while queue:
        pos = queue.popleft()
        d = distances[pos]
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            npos = (pos[0] + dx, pos[1] + dy)
            if npos not in distances and npos not in blocked:
                distances[npos] = d + 1
                queue.append(npos)
    return distances


def bfs(
    start: tuple[int, int],
    goal: tuple[int, int],
    blocked: set[tuple[int, int]],
) -> Optional[tuple[int, int]]:
    """BFS pathfinding from start to goal. Returns next position to move to.

    Searches backwards from goal so the returned position is the first step
    on the shortest path from start toward goal.

    Args:
        start: (x, y) current position.
        goal: (x, y) target position.
        blocked: set of (x, y) impassable positions.

    Returns:
        (x, y) next position to step to, or None if start == goal or no path.
    """
    if start == goal:
        return None
    queue = deque([(goal, [])])
    visited = {goal}
    while queue:
        pos, path = queue.popleft()
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            npos = (pos[0] + dx, pos[1] + dy)
            if npos in visited:
                continue
            if npos != start and npos in blocked:
                continue
            visited.add(npos)
            if npos == start:
                return pos
            queue.append((npos, path + [pos]))
    return None


def bfs_full_path(
    start: tuple[int, int],
    goal: tuple[int, int],
    blocked: set[tuple[int, int]],
) -> list[tuple[int, int]]:
    """BFS returning the full shortest path from start to goal (inclusive).

    Args:
        start: (x, y) starting position.
        goal: (x, y) target position.
        blocked: set of (x, y) impassable positions.

    Returns:
        list of (x, y) positions from start to goal inclusive,
        or empty list if no path exists. If start == goal, returns [start].
    """
    if start == goal:
        return [start]
    parent: dict[tuple[int, int], Optional[tuple[int, int]]] = {start: None}
    queue = deque([start])
    while queue:
        pos = queue.popleft()
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            npos = (pos[0] + dx, pos[1] + dy)
            if npos not in parent and npos not in blocked:
                parent[npos] = pos
                if npos == goal:
                    # Reconstruct path
                    path: list[tuple[int, int]] = []
                    cur: Optional[tuple[int, int]] = goal
                    while cur is not None:
                        path.append(cur)
                        cur = parent[cur]
                    path.reverse()
                    return path
                queue.append(npos)
    return []


def bfs_temporal(
    start: tuple[int, int],
    goal: tuple[int, int],
    blocked_static: set[tuple[int, int]],
    moving_obstacles: list[tuple[tuple[int, int], tuple[int, int]]],
) -> Optional[tuple[int, int]]:
    """BFS pathfinding that avoids both current and predicted positions of
    moving obstacles (other bots).

    This is a two-step temporal planner:
    - At time step 0 (this turn), avoid both current_pos and predicted_next_pos
      of all moving obstacles.
    - At time step 1+ (future turns), avoid only predicted_next_pos since bots
      will have moved by then.

    If the temporally-aware path fails (all routes blocked), falls back to
    standard BFS avoiding only current positions.

    Args:
        start: (x, y) current position.
        goal: (x, y) target position.
        blocked_static: set of (x, y) static impassable positions (walls, shelves).
        moving_obstacles: list of (current_pos, predicted_next_pos) tuples for
            other bots. Each element describes where a bot is now and where it
            is expected to be next turn.

    Returns:
        (x, y) next position to move to, or None if start == goal or no path.
    """
    if start == goal:
        return None

    if not moving_obstacles:
        return bfs(start, goal, blocked_static)

    # Positions blocked at time step 0: both current and predicted positions
    current_positions: set[tuple[int, int]] = set()
    predicted_positions: set[tuple[int, int]] = set()
    for cur_pos, pred_pos in moving_obstacles:
        current_positions.add(cur_pos)
        predicted_positions.add(pred_pos)

    # Step 0 blocked: static + current + predicted (avoid collisions and
    # head-on conflicts)
    step0_blocked = blocked_static | current_positions | predicted_positions

    # Step 1+ blocked: static + predicted only (bots have moved away from
    # current positions)
    future_blocked = blocked_static | predicted_positions

    # Time-expanded BFS: (position, time_step)
    # We only distinguish step 0 vs step 1+ for blocking rules
    # Use BFS from goal backward to find the first move from start
    # Time step 0 = the move we're about to make (start -> next_pos)
    # Time step 1+ = subsequent moves

    # Forward BFS from start
    # State: (pos, time_step) but we cap time_step at 1 since blocking rules
    # are the same for all steps >= 1
    visited: set[tuple[tuple[int, int], int]] = {(start, 0)}
    queue: deque[tuple[tuple[int, int], int, Optional[tuple[int, int]]]] = deque(
        [(start, 0, None)]
    )

    while queue:
        pos, t, first_move = queue.popleft()
        next_t = min(t + 1, 1)  # Cap at 1 since rules are same for t >= 1
        blocked_now = step0_blocked if t == 0 else future_blocked

        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            npos = (pos[0] + dx, pos[1] + dy)
            if npos in blocked_now:
                continue
            state_key = (npos, next_t)
            if state_key in visited:
                continue
            visited.add(state_key)

            next_first = first_move if first_move is not None else npos

            if npos == goal:
                return next_first

            queue.append((npos, next_t, next_first))

    # Fallback: try standard BFS avoiding only static + current positions
    # (less safe but at least makes progress)
    fallback_blocked = blocked_static | current_positions
    return bfs(start, goal, fallback_blocked)


def direction_to(sx: int, sy: int, tx: int, ty: int) -> str:
    """Convert a single step into a move action string.

    Args:
        sx, sy: source position.
        tx, ty: target position (must be adjacent).

    Returns:
        One of "move_right", "move_left", "move_down", "move_up", or "wait".
    """
    dx, dy = tx - sx, ty - sy
    if dx == 1:
        return "move_right"
    if dx == -1:
        return "move_left"
    if dy == 1:
        return "move_down"
    if dy == -1:
        return "move_up"
    return "wait"


def _predict_pos(bx: int, by: int, action: str) -> tuple[int, int]:
    """Predict bot position after an action."""
    if action == "move_up":
        return (bx, by - 1)
    if action == "move_down":
        return (bx, by + 1)
    if action == "move_left":
        return (bx - 1, by)
    if action == "move_right":
        return (bx + 1, by)
    return (bx, by)



def find_adjacent_positions(
    ix: int,
    iy: int,
    blocked_static: set[tuple[int, int]],
) -> list[tuple[int, int]]:
    """Find walkable positions adjacent to an item shelf."""
    adj: list[tuple[int, int]] = []
    for dx, dy in DIRECTIONS:
        pos = (ix + dx, iy + dy)
        if pos not in blocked_static:
            adj.append(pos)
    return adj
