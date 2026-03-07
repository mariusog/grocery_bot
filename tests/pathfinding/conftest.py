"""Shared fixtures and helpers for pathfinding tests."""


def _bounded_blocked(width=11, height=9):
    """Create a border-walled blocked set so bfs_all terminates."""
    blocked = set()
    for x in range(-1, width + 1):
        blocked.add((x, -1))
        blocked.add((x, height))
    for y in range(-1, height + 1):
        blocked.add((-1, y))
        blocked.add((width, y))
    return blocked
