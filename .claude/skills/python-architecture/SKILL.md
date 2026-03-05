---
name: python-architecture
description: Guides Python project architecture decisions and patterns for AI/ML and algorithmic projects. Use when deciding where to put code, choosing between patterns, designing module structure, or when user mentions architecture, code organization, or design patterns.
---

# Python Project Architecture Patterns

## Overview

Python projects benefit from clear module organization, separation of concerns, and simple patterns that avoid over-engineering. This skill guides architectural decisions for clean, maintainable Python code.

## Architecture Decision Tree

```
Where should this code go?
│
├─ Is it a pure algorithm (pathfinding, optimization, math)?
│   └─ → Dedicated module (e.g., pathfinding.py, optimizer.py)
│
├─ Is it data transformation or processing?
│   └─ → Pipeline module or function chain
│
├─ Is it configuration or constants?
│   └─ → config.py or module-level constants
│
├─ Is it shared utility logic?
│   └─ → utils.py (keep small) or domain-specific module
│
├─ Is it I/O (files, network, database)?
│   └─ → Separate I/O module, keep business logic pure
│
├─ Is it test infrastructure?
│   └─ → conftest.py or test helpers module
│
├─ Is it a CLI entry point?
│   └─ → __main__.py or cli.py
│
└─ Is it ML model training/inference?
    └─ → models/ directory with train.py, predict.py
```

## Module Organization

### Small Project (< 10 files)

```
project/
├── bot.py              # Main logic
├── pathfinding.py      # Algorithm module
├── simulator.py        # Game simulation
├── config.py           # Constants and configuration
├── test_bot.py         # Tests
├── test_pathfinding.py
├── requirements.txt
└── README.md
```

### Medium Project (10-30 files)

```
project/
├── src/
│   ├── __init__.py
│   ├── bot.py
│   ├── pathfinding.py
│   ├── optimizer.py
│   ├── state.py          # State management / data classes
│   └── utils.py
├── tests/
│   ├── conftest.py       # Shared fixtures
│   ├── test_bot.py
│   ├── test_pathfinding.py
│   └── test_optimizer.py
├── pyproject.toml
└── README.md
```

### ML/Data Science Project

```
project/
├── data/                 # Raw and processed data
├── notebooks/            # Exploration and analysis
├── src/
│   ├── data/             # Data loading and processing
│   │   ├── __init__.py
│   │   ├── loader.py
│   │   └── transforms.py
│   ├── models/           # Model definitions
│   │   ├── __init__.py
│   │   ├── train.py
│   │   └── predict.py
│   ├── features/         # Feature engineering
│   │   ├── __init__.py
│   │   └── build_features.py
│   └── utils.py
├── tests/
├── configs/              # Training configs (YAML/TOML)
├── pyproject.toml
└── README.md
```

## Core Principles

### 1. Separate Pure Logic from I/O

```python
# GOOD: Pure function — easy to test
def decide_actions(state: dict) -> list[dict]:
    """Pure decision logic. No I/O."""
    ...

# GOOD: I/O wrapper calls pure logic
async def play():
    async for message in websocket:
        state = json.loads(message)
        actions = decide_actions(state)  # Pure
        await websocket.send(json.dumps(actions))  # I/O
```

```python
# BAD: Mixing I/O with logic
def decide_and_send(websocket, state):
    actions = compute(state)
    websocket.send(actions)  # Can't test without a real socket
```

### 2. Functions Over Classes (When Appropriate)

Python isn't Java. Don't create classes when functions suffice:

```python
# BAD: Unnecessary class
class PathFinder:
    def __init__(self):
        pass
    def find_path(self, start, goal, blocked):
        return bfs(start, goal, blocked)

# GOOD: Just a function
def find_path(start, goal, blocked):
    return bfs(start, goal, blocked)
```

Use classes when you have:
- Shared state across multiple methods
- Multiple instances with different configurations
- Need for inheritance or protocols

### 3. Dataclasses for Structured Data

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class Position:
    x: int
    y: int

@dataclass
class BotState:
    id: int
    position: Position
    inventory: list[str]
```

### 4. Module-Level State (With Care)

For performance-critical code, module-level caches are fine:

```python
# Module-level cache — fast, simple
_dist_cache: dict[tuple, dict] = {}

def get_distances(source):
    if source not in _dist_cache:
        _dist_cache[source] = bfs_all(source)
    return _dist_cache[source]

def reset():
    """Call between games."""
    _dist_cache.clear()
```

### 5. Type Hints for Public APIs

```python
from typing import Optional

def find_best_target(
    pos: tuple[int, int],
    items: list[dict],
    blocked: set[tuple[int, int]],
) -> Optional[tuple[dict, float]]:
    """Find closest reachable item.

    Returns (item, distance) or None if unreachable.
    """
```

## When NOT to Abstract

| Situation | Keep It Simple | Don't Create |
|-----------|----------------|--------------|
| Used only once | Inline the code | Separate module |
| Simple function < 10 lines | Keep in current file | Utility module |
| One-off data transform | List comprehension | Pipeline class |
| Simple config | Module constants | Config framework |

### Signs of Over-Engineering

```python
# OVER-ENGINEERED: Abstract base class for one implementation
class BasePathfinder(ABC):
    @abstractmethod
    def find_path(self, start, goal): ...

class BFSPathfinder(BasePathfinder):
    def find_path(self, start, goal):
        return bfs(start, goal)

# KEEP IT SIMPLE
def find_path(start, goal, blocked):
    return bfs(start, goal, blocked)
```

### When TO Abstract

| Signal | Action |
|--------|--------|
| Same code in 3+ places | Extract to shared function |
| Module > 500 lines | Split into focused modules |
| Function > 50 lines | Extract helper functions |
| Complex conditionals | Extract to strategy dict or function |
| Multiple data representations | Use dataclass |

## Anti-Patterns to Avoid

| Anti-Pattern | Problem | Solution |
|--------------|---------|----------|
| God module | One file with everything | Split by responsibility |
| Premature abstraction | ABC for 1 implementation | Use a plain function |
| Global mutable state everywhere | Hard to test, race conditions | Limit scope, provide reset |
| Stringly typed | Magic strings everywhere | Use enums or constants |
| Nested dict soup | `data["a"]["b"]["c"]` | Use dataclasses or TypedDict |
| Import-time side effects | Module import triggers I/O | Defer to explicit init function |

## Testing Strategy by Module Type

| Module Type | Test Approach | Focus |
|-------------|---------------|-------|
| Pure functions | Direct unit tests | Input → output correctness |
| Algorithms | Parametrized tests | Edge cases, complexity |
| State management | Setup/teardown fixtures | State transitions |
| I/O wrappers | Mocks and integration tests | Error handling |
| CLI entry points | subprocess or click testing | Argument parsing |

## Related Skills

| Category | Skills |
|----------|--------|
| **Code Quality** | `code-review`, `refactor`, `lint` |
| **Testing** | `tdd-cycle`, `test-coverage` |
| **Performance** | `caching-strategies`, `performance-optimization` |
| **Security** | `security-scan` |
| **Documentation** | `update-documentation` |
