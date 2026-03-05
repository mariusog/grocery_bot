---
name: test-coverage
description: Ensure adequate test coverage for changed code. Identifies relevant tests, runs them, and checks coverage. Use when the user asks to check test coverage, run tests, or verify specs.
---

# Test Coverage Skill

Ensure changed code has adequate test coverage and all tests pass.

## Scope

This skill applies to files changed in the current branch compared to `main` (or `origin/main`).
Identify changed files with: `git diff --name-only origin/main...HEAD`

## Project Testing Conventions

This project uses:
- **pytest** as the test framework
- Test files follow `test_*.py` naming convention
- Helper functions (e.g., `make_state`, `reset_bot`) for building test fixtures
- Class-based test grouping (e.g., `class TestFeatureName`)
- Global state reset between tests (module caches, etc.)

## Step 1: Identify Relevant Tests

For each changed file, find corresponding test files:

### Mapping Source to Tests
- `module.py` → `test_module.py`
- `bot.py` → `test_bot.py`
- `simulator.py` → `test_simulator.py` or simulation tests in `test_bot.py`
- `utils/*.py` → `tests/test_utils.py` or `tests/test_<util_name>.py`

Use grep to find test references:
```bash
grep -r "from module import\|import module" test_*.py tests/
```

## Step 2: Baseline Test Run

Run identified tests to ensure we start green:
```bash
pytest <list of test files> -v
```

If tests fail:
- **STOP** — Do not proceed with other quality steps
- Report failing tests to the user
- Broken tests must be fixed before continuing

## Step 3: Coverage Analysis

For each changed file, verify test coverage:

### Check for Missing Tests
- Does every new public function have a corresponding test?
- Are new classes covered by tests?
- Are new algorithms tested with representative inputs?

### Check for Missing Scenarios
For existing tests, verify coverage of:
- Happy path (normal operation)
- Edge cases (empty inputs, boundary values, None/zero)
- Error paths (invalid inputs, unreachable goals, timeouts)
- State transitions (before/after mutations)

### Add Missing Tests
If coverage is insufficient:
1. Write unit tests for new/changed public functions
2. Write integration tests for new workflows
3. Add edge case and error path tests
4. Use `@pytest.mark.parametrize` for multiple input scenarios

### Coverage Tool (if available)
```bash
pytest --cov=<module> --cov-report=term-missing <test files>
```

## Step 4: Run Full Test Suite

Run all relevant tests:
```bash
pytest -v
```

Ensure all tests pass before completing.

## Step 5: Verify No Regressions

If refactoring was done alongside coverage work:
- Run the full test suite to catch regressions
- Check that no existing tests were broken

## Completion

Report:
- Number of test files identified
- Number of tests run
- Pass/fail status
- Any new tests added
- Coverage gaps that still need attention
