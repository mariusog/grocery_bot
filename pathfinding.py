"""Pure pathfinding functions and movement helpers."""

from collections import deque

DIRECTIONS = [(0, -1), (0, 1), (-1, 0), (1, 0)]


def bfs_all(source, blocked):
    """BFS from source to ALL reachable cells. Returns {pos: distance}."""
    distances = {source: 0}
    queue = deque([source])
    while queue:
        pos = queue.popleft()
        d = distances[pos]
        for dx, dy in DIRECTIONS:
            npos = (pos[0] + dx, pos[1] + dy)
            if npos not in distances and npos not in blocked:
                distances[npos] = d + 1
                queue.append(npos)
    return distances


def bfs(start, goal, blocked):
    """BFS pathfinding. Returns next position to move to, or None."""
    if start == goal:
        return None
    queue = deque([(goal, [])])
    visited = {goal}
    while queue:
        pos, path = queue.popleft()
        for dx, dy in DIRECTIONS:
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


def direction_to(sx, sy, tx, ty):
    """Convert a single step into a move action string."""
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


def _predict_pos(bx, by, action):
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


def get_needed_items(order):
    """Get dict of {item_type: count_still_needed} for an order."""
    needed = {}
    for item in order["items_required"]:
        needed[item] = needed.get(item, 0) + 1
    for item in order["items_delivered"]:
        needed[item] = needed.get(item, 0) - 1
    return {k: v for k, v in needed.items() if v > 0}


def find_adjacent_positions(ix, iy, blocked_static):
    """Find walkable positions adjacent to an item shelf."""
    adj = []
    for dx, dy in DIRECTIONS:
        pos = (ix + dx, iy + dy)
        if pos not in blocked_static:
            adj.append(pos)
    return adj
