---
name: caching-strategies
description: Implements Python caching patterns for performance optimization. Use when adding memoization, precomputation, result caching, or when user mentions caching, performance, cache keys, or memoization.
---

# Caching Strategies for Python

## Overview

For algorithmic and data-processing Python applications, focus on these caching layers:
- **Precomputation**: Compute expensive results once at startup
- **Memoization**: Cache function results by arguments
- **Module-level caching**: Global dicts for reusable lookups
- **Disk caching**: Persist results across runs (joblib, shelve)

## Memoization

### functools.lru_cache

Best for pure functions with hashable arguments:

```python
from functools import lru_cache

@lru_cache(maxsize=None)  # Unbounded cache
def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

# Check cache stats
print(fibonacci.cache_info())
# CacheInfo(hits=97, misses=100, maxsize=None, currsize=100)

# Clear if needed
fibonacci.cache_clear()
```

### functools.cache (Python 3.9+)

Shorthand for `lru_cache(maxsize=None)`:

```python
from functools import cache

@cache
def expensive_pure_function(x, y):
    return complex_calculation(x, y)
```

### When lru_cache Won't Work

For unhashable arguments (lists, dicts, sets), convert to hashable:

```python
@lru_cache(maxsize=256)
def find_path(start, goal, blocked_frozenset):
    blocked = blocked_frozenset  # frozenset is hashable
    return bfs(start, goal, blocked)

# Call with frozenset
path = find_path((0, 0), (5, 5), frozenset(blocked_cells))
```

## Module-Level Dict Caching

For caches that need manual management:

```python
_dist_cache = {}  # {source_pos: {dest_pos: distance}}

def get_distances_from(source, blocked):
    """Get cached BFS distance map from source."""
    if source not in _dist_cache:
        _dist_cache[source] = bfs_all(source, blocked)
    return _dist_cache[source]

def clear_caches():
    """Reset caches between games/runs."""
    global _dist_cache
    _dist_cache = {}
```

### Cache with Computed Keys

```python
_result_cache = {}

def cached_computation(config):
    key = (config["width"], config["height"], frozenset(config["walls"]))
    if key not in _result_cache:
        _result_cache[key] = expensive_setup(config)
    return _result_cache[key]
```

## Precomputation Pattern

Compute once at initialization, use many times:

```python
_blocked_static = None
_adj_cache = {}

def init_static(state):
    """Compute static data on round 0 — map never changes."""
    global _blocked_static, _adj_cache

    walls = {tuple(w) for w in state["grid"]["walls"]}
    items = {tuple(it["position"]) for it in state["items"]}
    _blocked_static = walls | items | _compute_boundaries(state)

    # Precompute adjacency for every item position
    for it in state["items"]:
        pos = tuple(it["position"])
        _adj_cache[pos] = [
            (pos[0] + dx, pos[1] + dy)
            for dx, dy in [(0, -1), (0, 1), (-1, 0), (1, 0)]
            if (pos[0] + dx, pos[1] + dy) not in _blocked_static
        ]
```

## Disk Caching

### joblib (for ML/data science)

```python
from joblib import Memory

memory = Memory("./cache", verbose=0)

@memory.cache
def train_model(X, y, params):
    """Cached across runs — recomputes only if inputs change."""
    model = SomeModel(**params)
    model.fit(X, y)
    return model
```

### shelve (simple key-value persistence)

```python
import shelve

def load_or_compute(key, compute_fn):
    with shelve.open("cache.db") as db:
        if key not in db:
            db[key] = compute_fn()
        return db[key]
```

### pickle (manual serialization)

```python
import pickle
from pathlib import Path

CACHE_PATH = Path("cache/distances.pkl")

def load_distances():
    if CACHE_PATH.exists():
        return pickle.loads(CACHE_PATH.read_bytes())
    distances = compute_all_distances()
    CACHE_PATH.parent.mkdir(exist_ok=True)
    CACHE_PATH.write_bytes(pickle.dumps(distances))
    return distances
```

## Cache Invalidation

### Time-Based

```python
import time

_cache = {}
_cache_time = {}
CACHE_TTL = 300  # 5 minutes

def get_cached(key, compute_fn):
    now = time.time()
    if key in _cache and (now - _cache_time[key]) < CACHE_TTL:
        return _cache[key]
    result = compute_fn()
    _cache[key] = result
    _cache_time[key] = now
    return result
```

### Event-Based

```python
def on_new_game():
    """Clear all caches when starting a new game."""
    _dist_cache.clear()
    _adj_cache.clear()
    fibonacci.cache_clear()
```

## Testing Caching

```python
def test_cache_returns_same_result():
    result1 = get_distances_from((0, 0), blocked)
    result2 = get_distances_from((0, 0), blocked)
    assert result1 is result2  # Same object (cached)

def test_cache_invalidation():
    get_distances_from((0, 0), blocked)
    clear_caches()
    assert (0, 0) not in _dist_cache
```

## Checklist

- [ ] Pure functions use `@lru_cache` or `@cache`
- [ ] Static data precomputed once at initialization
- [ ] Cache keys are hashable (tuples, frozensets, not lists/dicts)
- [ ] Caches cleared between runs/games/sessions
- [ ] Cache hit rates monitored for key caches
- [ ] No unbounded caches that could cause memory issues
- [ ] Disk caching for expensive ML training or data processing
