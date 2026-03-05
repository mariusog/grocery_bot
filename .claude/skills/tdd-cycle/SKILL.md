---
name: tdd-cycle
description: Guides Test-Driven Development workflow with Red-Green-Refactor cycle using pytest. Use when the user wants to implement a feature using TDD, write tests first, follow test-driven practices, or mentions red-green-refactor.
---

# TDD Cycle Skill

## Overview

This skill guides you through the Test-Driven Development cycle:
1. **RED**: Write a failing test that describes desired behavior
2. **GREEN**: Write minimal code to pass the test
3. **REFACTOR**: Improve code while keeping tests green

## Workflow Checklist

```
TDD Progress:
- [ ] Step 1: Understand the requirement
- [ ] Step 2: Choose test type (unit/integration/e2e)
- [ ] Step 3: Write failing test (RED)
- [ ] Step 4: Verify test fails correctly
- [ ] Step 5: Implement minimal code (GREEN)
- [ ] Step 6: Verify test passes
- [ ] Step 7: Refactor if needed
- [ ] Step 8: Verify tests still pass
```

## Step 1: Requirement Analysis

Before writing any code, understand:
- What is the expected input?
- What is the expected output/behavior?
- What are the edge cases?
- What errors should be handled?

Ask clarifying questions if requirements are ambiguous.

## Step 2: Choose Test Type

| Test Type | Use For | Location | Example |
|-----------|---------|----------|---------|
| Unit test | Pure functions, class methods | `test_*.py` | Testing `calculate_score()` |
| Integration test | Module interactions, pipelines | `test_*.py` | Testing bot decision flow |
| Simulation test | Full game/system behavior | `test_*.py` | Testing end-to-end game play |
| Parametrized test | Same logic, many inputs | `test_*.py` | Testing pathfinding edge cases |

## Step 3: Write Failing Test (RED)

### Test Structure

```python
import pytest
from module_under_test import function_or_class


class TestClassName:
    """Tests for ClassName behavior."""

    def test_expected_behavior(self):
        result = function_or_class(input_value)
        assert result == expected_value

    def test_edge_case(self):
        with pytest.raises(ValueError, match="specific message"):
            function_or_class(invalid_input)

    @pytest.mark.parametrize("input_val,expected", [
        (1, "one"),
        (2, "two"),
        (3, "three"),
    ])
    def test_multiple_cases(self, input_val, expected):
        assert function_or_class(input_val) == expected
```

### Good Test Characteristics

- **One behavior per test**: Each test function tests one thing
- **Clear naming**: `test_<what>_<condition>_<expected>` pattern
- **Minimal setup**: Only create data needed for the specific test
- **Fast execution**: Mock external dependencies, avoid I/O
- **Independent**: Tests don't depend on order or shared mutable state

### Test Data

Use helper functions or fixtures for test data:

```python
@pytest.fixture
def sample_state():
    """Build a minimal game state for testing."""
    return {
        "bots": [{"id": 0, "position": [3, 3], "inventory": []}],
        "items": [],
        "orders": [],
        "drop_off": [1, 8],
        ...
    }

def test_bot_waits_with_no_orders(sample_state):
    actions = decide_actions(sample_state)
    assert actions[0]["action"] == "wait"
```

## Step 4: Verify Failure

Run the test:
```bash
pytest path/to/test_file.py::TestClass::test_name -v
```

The test MUST fail with a clear message. If it passes immediately:
- The behavior already exists (check if intentional)
- The test is wrong (not testing what you think)

## Step 5: Implement (GREEN)

Write the MINIMUM code to pass:
- No optimization yet
- No edge case handling (unless that's what you're testing)
- No refactoring
- Just make it work

## Step 6: Verify Pass

```bash
pytest path/to/test_file.py::TestClass::test_name -v
```

It MUST pass. If it fails:
1. Read the error carefully
2. Fix the implementation (not the test, unless the test was wrong)
3. Run again

## Step 7: Refactor

Improve the code while keeping tests green. See the `refactor` skill for patterns.

### Refactoring Rules
1. Make ONE change at a time
2. Run tests after EACH change
3. If tests fail, undo and try a different approach
4. Stop when code is clean (don't over-engineer)

## Step 8: Final Verification

Run all related tests:
```bash
pytest path/to/test_file.py -v
```

All tests must pass.

## Common Patterns

### Testing Pure Functions

```python
def test_direction_to_returns_correct_move():
    assert direction_to(0, 0, 1, 0) == "move_right"
    assert direction_to(0, 0, -1, 0) == "move_left"
    assert direction_to(0, 0, 0, 1) == "move_down"
    assert direction_to(0, 0, 0, -1) == "move_up"
```

### Testing with Fixtures and Reset

```python
@pytest.fixture(autouse=True)
def reset_global_state():
    """Reset module globals between tests."""
    module._cache = {}
    yield
    module._cache = {}
```

### Testing Algorithms

```python
class TestBFS:
    def test_finds_shortest_path(self):
        blocked = {(1, 0), (1, 1)}
        result = bfs((0, 0), (2, 0), blocked)
        assert result is not None

    def test_returns_none_when_no_path(self):
        blocked = {(1, 0), (0, 1)}  # Completely blocked
        result = bfs((0, 0), (2, 2), blocked)
        assert result is None
```

### Testing with Mocks

```python
from unittest.mock import patch, MagicMock

def test_api_call_handles_timeout():
    with patch("module.requests.get", side_effect=TimeoutError):
        result = fetch_data("http://example.com")
        assert result is None
```

## Anti-Patterns to Avoid

1. **Testing implementation, not behavior**: Test what it does, not how
2. **Too many assertions**: Split into separate test functions
3. **Brittle tests**: Don't test exact error messages or timestamps
4. **Slow tests**: Mock external services, avoid unnecessary I/O
5. **Mystery data**: Make test data explicit and visible in each test
