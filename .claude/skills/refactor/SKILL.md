---
name: refactor
description: Refactor code for clarity and maintainability. Includes control flow improvements, constant extraction, and comment cleanup. Use when the user asks to refactor code, clean up code, or improve code structure.
---

# Refactor Skill

Improve code clarity and maintainability through targeted refactoring.

## Scope

This skill applies to files changed in the current branch compared to `main` (or `origin/main`).
Identify changed files with: `git diff --name-only origin/main...HEAD`

## Step 1: Control Flow Refactoring

Review changed files and improve control flow:

### Replace Conditionals with Dictionaries
Before:
```python
def status_color(status):
    if status == "success":
        return "green"
    elif status == "warning":
        return "yellow"
    elif status == "error":
        return "red"
    else:
        return "gray"
```

After:
```python
STATUS_COLORS = {
    "success": "green",
    "warning": "yellow",
    "error": "red",
}

def status_color(status):
    return STATUS_COLORS.get(status, "gray")
```

### Use Early Returns
Before:
```python
def process(data):
    if data is not None:
        if data.is_valid():
            # long processing logic
            pass
```

After:
```python
def process(data):
    if data is None:
        return
    if not data.is_valid():
        return
    # long processing logic
```

### Prefer Guard Clauses
- Move precondition checks to the top of functions
- Return early for invalid states
- Reduce nesting depth

### Simplify with Python Idioms
Before:
```python
result = []
for item in items:
    if item.is_active():
        result.append(item.name)
```

After:
```python
result = [item.name for item in items if item.is_active()]
```

## Step 2: Extract Constants

Find and fix magic numbers and strings:

### Magic Numbers
Before:
```python
def calculate_score(value):
    return value * 1.15 + 50
```

After:
```python
SCORE_MULTIPLIER = 1.15
BASE_SCORE_BONUS = 50

def calculate_score(value):
    return value * SCORE_MULTIPLIER + BASE_SCORE_BONUS
```

### Placement Guidelines
- Module-level constants: ALL_CAPS at the top of the module
- Class-specific constants: Class attributes or module-level
- Configuration values: Environment variables, config files, or dataclass defaults

## Step 3: Comment Cleanup

Review and clean up comments in changed files:

### Remove Unnecessary Comments
Delete comments that:
- Simply describe what the code does (code should be self-documenting)
- Restate the function name or variable name
- Are outdated or no longer accurate
- Are commented-out code

Before:
```python
# Calculate the total price
def calculate_total_price(items):
    # Loop through items and sum prices
    total = 0
    for item in items:
        # Get the price
        total += item.price
    return total
```

After:
```python
def calculate_total_price(items):
    return sum(item.price for item in items)
```

### Keep Valuable Comments
Preserve comments that:
- Explain WHY something is done a certain way
- Document non-obvious business logic or algorithm choices
- Warn about edge cases or gotchas
- Reference external documentation or tickets

Good example:
```python
# Using insertion sort here because the array is nearly sorted
# and small (< 10 elements), making it faster than quicksort
def sort_recent_items(items):
    ...
```

## Step 4: File and Naming Conventions

Check that changed files follow conventions:

### Python Conventions
- Modules: `snake_case.py`
- Classes: `PascalCase`
- Functions/variables: `snake_case`
- Constants: `UPPER_SNAKE_CASE`
- Private: `_leading_underscore`
- Test files: `test_*.py` or `*_test.py`

## Step 5: Verify Changes

After refactoring:
- Run tests to verify behavior is unchanged: `pytest`
- Run linter to verify style: `ruff check`
- Check that refactored code passes type checking if applicable

## Completion

Report:
- Number of control flow improvements made
- Number of constants extracted
- Number of comments cleaned up
- Any areas that could benefit from further refactoring
