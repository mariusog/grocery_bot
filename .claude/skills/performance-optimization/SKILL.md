---
name: performance-optimization
description: Identifies and fixes Python performance issues including algorithmic complexity, memory usage, and profiling. Use when optimizing code, fixing slow functions, improving response times, or when user mentions performance, slow, optimization, or profiling.
---

# Performance Optimization for Python

## Overview

Performance optimization focuses on:
- Algorithmic complexity reduction
- Data structure selection
- Memory management
- CPU profiling and hot path optimization
- Caching and precomputation

## Quick Start

Useful profiling tools:
- `cProfile` / `profile` — Built-in CPU profiling
- `timeit` — Micro-benchmarking
- `memory_profiler` — Memory usage analysis
- `line_profiler` — Line-by-line timing
- `py-spy` — Sampling profiler (no code changes)

## Algorithmic Complexity

### Common Fixes

```python
# BAD: O(n²) — checking membership in a list
if item in large_list:  # O(n) per lookup

# GOOD: O(1) — use a set
large_set = set(large_list)
if item in large_set:  # O(1) per lookup
```

```python
# BAD: O(n²) — nested loop for matching
for a in list_a:
    for b in list_b:
        if a.id == b.id:
            process(a, b)

# GOOD: O(n) — index one side with a dict
b_by_id = {b.id: b for b in list_b}
for a in list_a:
    if a.id in b_by_id:
        process(a, b_by_id[a.id])
```

```python
# BAD: Repeated BFS/computation
for target in targets:
    path = bfs(start, target, blocked)  # Recomputes from scratch

# GOOD: Single BFS, cache results
distances = bfs_all(start, blocked)  # One BFS, all distances
for target in targets:
    d = distances.get(target, float("inf"))  # O(1) lookup
```

### When to Optimize

| Signal | Action |
|--------|--------|
| Function called 1000+ times per decision | Profile and optimize |
| O(n²) in a hot loop | Reduce to O(n log n) or O(n) |
| Same computation repeated | Cache or precompute |
| Large data copied unnecessarily | Use views or generators |

## Data Structure Selection

| Need | Use | Not |
|------|-----|-----|
| Fast membership test | `set`, `frozenset` | `list` |
| Key-value lookup | `dict` | list of tuples |
| FIFO queue | `collections.deque` | `list` (pop(0) is O(n)) |
| Counting | `collections.Counter` | manual dict |
| Default values | `collections.defaultdict` | `dict.setdefault()` |
| Sorted access | `heapq` or `sortedcontainers` | repeated `sorted()` |
| Immutable record | `tuple` or `NamedTuple` | `dict` |

## Caching Patterns

### functools.lru_cache

```python
from functools import lru_cache

@lru_cache(maxsize=1024)
def expensive_computation(x, y):
    # Must use hashable arguments
    return complex_calculation(x, y)
```

### Manual Caching with Dicts

```python
_cache = {}

def get_distances(source, blocked_key):
    if source not in _cache:
        _cache[source] = bfs_all(source, blocked)
    return _cache[source]
```

### Precomputation

```python
# Compute once, use many times
def init_static(state):
    """Precompute on round 0 — map is static."""
    global _blocked, _adjacency
    _blocked = compute_blocked_cells(state)
    _adjacency = {pos: get_neighbors(pos) for pos in all_positions}
```

## Memory Optimization

### Generators Over Lists

```python
# BAD: Creates entire list in memory
squares = [x**2 for x in range(1_000_000)]

# GOOD: Generates values on demand
squares = (x**2 for x in range(1_000_000))
```

### __slots__ for Many Instances

```python
class Point:
    __slots__ = ("x", "y")
    def __init__(self, x, y):
        self.x = x
        self.y = y
# Uses ~40% less memory than regular class
```

### Avoid Unnecessary Copies

```python
# BAD: Creates a new set every iteration
for bot in bots:
    blocked = blocked_static | {tuple(b["position"]) for b in other_bots}

# GOOD: Modify in place or reuse
blocked = set(blocked_static)
for b in other_bots:
    blocked.add(tuple(b["position"]))
```

## Profiling

### cProfile

```python
import cProfile

cProfile.run("decide_actions(state)", sort="cumulative")
```

### timeit for Micro-benchmarks

```python
import timeit

# Compare two approaches
t1 = timeit.timeit(lambda: approach_a(data), number=10000)
t2 = timeit.timeit(lambda: approach_b(data), number=10000)
print(f"A: {t1:.4f}s, B: {t2:.4f}s")
```

### Line Profiler

```bash
pip install line_profiler
kernprof -l -v script.py
```

## Testing for Performance

### Timing Assertions

```python
import time

def test_decide_actions_within_budget():
    """Decision must complete within 100ms for real-time play."""
    state = make_large_state()
    start = time.perf_counter()
    decide_actions(state)
    elapsed = time.perf_counter() - start
    assert elapsed < 0.1, f"Too slow: {elapsed:.3f}s"
```

### Complexity Assertions

```python
def test_bfs_scales_linearly():
    """BFS should scale with grid size, not quadratically."""
    times = []
    for size in [10, 20, 40]:
        state = make_state(width=size, height=size)
        start = time.perf_counter()
        bfs_all((0, 0), set())
        times.append(time.perf_counter() - start)

    # Doubling grid size should roughly 4x time (O(V+E)), not 16x
    ratio = times[2] / times[1]
    assert ratio < 8, f"Scaling too fast: {ratio:.1f}x"
```

## Performance Checklist

- [ ] Hot paths profiled and optimized
- [ ] Sets used for membership testing (not lists)
- [ ] Dicts used for key-value lookups
- [ ] Expensive computations cached or precomputed
- [ ] No unnecessary data copies in loops
- [ ] Generators used for large sequences
- [ ] BFS/pathfinding results cached when map is static
- [ ] Algorithm complexity documented for critical functions

## Quick Fixes Reference

| Problem | Solution |
|---------|----------|
| Slow membership test | Convert list to set |
| Repeated BFS from same source | Cache distance maps |
| O(n²) matching | Index one side with dict |
| Large list built then iterated | Use generator |
| Repeated sorting | Use heapq or sorted container |
| String concatenation in loop | Use `"".join()` or list append |
| Repeated dict.get() with default | Use defaultdict |
