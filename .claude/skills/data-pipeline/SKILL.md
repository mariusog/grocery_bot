---
name: data-pipeline
description: Creates data processing pipelines and transformation patterns for Python. Use when building data transforms, processing chains, ETL workflows, or when user mentions data pipeline, data processing, feature engineering, or data transformation.
---

# Data Pipeline Patterns for Python

## Overview

Data pipelines transform raw inputs into useful outputs through a chain of processing steps. This skill covers patterns for both algorithmic data processing (game state → decisions) and ML data pipelines (raw data → features → predictions).

## Pipeline Types

### 1. Function Chain (Simple)

For straightforward data transformations:

```python
def process_game_state(raw_state):
    """Transform raw game state into actionable data."""
    state = parse_state(raw_state)
    needed = compute_needed_items(state)
    candidates = find_candidates(state, needed)
    route = optimize_route(candidates)
    return generate_actions(state, route)
```

### 2. Pipeline as List of Steps

For configurable pipelines:

```python
def build_pipeline(steps):
    """Compose a pipeline from a list of transform functions."""
    def run(data):
        for step in steps:
            data = step(data)
        return data
    return run

# Define pipeline
pipeline = build_pipeline([
    normalize_positions,
    compute_distances,
    rank_candidates,
    select_targets,
])

result = pipeline(raw_data)
```

### 3. Generator Pipeline (Memory-Efficient)

For large datasets that don't fit in memory:

```python
def read_records(path):
    """Read records lazily from file."""
    with open(path) as f:
        for line in f:
            yield json.loads(line)

def filter_valid(records):
    for record in records:
        if record.get("valid"):
            yield record

def transform(records):
    for record in records:
        yield {
            "id": record["id"],
            "score": compute_score(record),
        }

# Compose — nothing runs until consumed
pipeline = transform(filter_valid(read_records("data.jsonl")))
results = list(pipeline)  # Or iterate without materializing
```

## State Processing Pattern

For game bots and real-time systems:

```python
from dataclasses import dataclass

@dataclass
class ProcessedState:
    """Intermediate state after processing raw game data."""
    bot_positions: dict[int, tuple[int, int]]
    needed_items: dict[str, int]
    item_candidates: list[tuple[dict, tuple[int, int], float]]
    drop_off: tuple[int, int]

def process_state(raw: dict) -> ProcessedState:
    """Transform raw game state into structured processed state."""
    bots = {b["id"]: tuple(b["position"]) for b in raw["bots"]}
    active = next(
        (o for o in raw["orders"] if o.get("status") == "active"),
        None,
    )
    needed = get_needed_items(active) if active else {}
    candidates = find_item_candidates(raw["items"], needed)

    return ProcessedState(
        bot_positions=bots,
        needed_items=needed,
        item_candidates=candidates,
        drop_off=tuple(raw["drop_off"]),
    )
```

## ML Feature Pipeline

### Pandas-Based

```python
import pandas as pd

def load_data(path: str) -> pd.DataFrame:
    return pd.read_csv(path)

def clean_data(df: pd.DataFrame) -> pd.DataFrame:
    return (
        df.dropna(subset=["target"])
        .drop_duplicates()
        .reset_index(drop=True)
    )

def engineer_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["distance"] = (df["x"] ** 2 + df["y"] ** 2) ** 0.5
    df["time_bucket"] = pd.cut(df["round"], bins=10, labels=False)
    return df

def prepare_dataset(path: str) -> pd.DataFrame:
    return (
        load_data(path)
        .pipe(clean_data)
        .pipe(engineer_features)
    )
```

### NumPy-Based (Performance)

```python
import numpy as np

def vectorized_distances(positions: np.ndarray, target: np.ndarray) -> np.ndarray:
    """Compute Euclidean distances from all positions to target.

    Args:
        positions: Array of shape (n, 2).
        target: Array of shape (2,).

    Returns:
        Array of shape (n,) with distances.
    """
    diff = positions - target
    return np.sqrt(np.sum(diff ** 2, axis=1))
```

## Testing Data Pipelines

### Test Each Step Independently

```python
def test_compute_needed_items():
    order = {
        "items_required": ["cheese", "bread", "cheese"],
        "items_delivered": ["cheese"],
    }
    needed = get_needed_items(order)
    assert needed == {"cheese": 1, "bread": 1}

def test_find_candidates_excludes_claimed():
    items = [{"id": "a", "type": "cheese", "position": [1, 1]}]
    claimed = {"a"}
    result = find_candidates(items, {"cheese": 1}, claimed)
    assert result == []
```

### Test End-to-End

```python
def test_full_pipeline():
    raw_state = make_state(
        bots=[{"id": 0, "position": [0, 0], "inventory": []}],
        items=[{"id": "a", "type": "cheese", "position": [1, 0]}],
        orders=[make_active_order(["cheese"])],
    )
    actions = decide_actions(raw_state)
    assert actions[0]["action"] == "pick_up"
```

### Test with Edge Cases

```python
@pytest.mark.parametrize("items,expected_count", [
    ([], 0),
    ([single_item], 1),
    ([item1, item2, item3], 3),
])
def test_candidate_count(items, expected_count):
    result = find_candidates(items, needed={"cheese": 10})
    assert len(result) == expected_count
```

## Checklist

- [ ] Each pipeline step is a pure function (input → output)
- [ ] Steps are testable independently
- [ ] Intermediate data structures are well-defined (dataclasses/TypedDict)
- [ ] Large datasets use generators, not lists
- [ ] NumPy/pandas vectorization used instead of Python loops where applicable
- [ ] Error handling at data boundaries (file I/O, API responses)
- [ ] Pipeline is composable — steps can be reordered or swapped
