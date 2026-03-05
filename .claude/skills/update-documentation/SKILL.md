---
name: update-documentation
description: Update project documentation to reflect code changes. Reviews README, docstrings, and technical documentation. Use when the user asks to update docs, document changes, or sync documentation.
---

# Update Documentation Skill

Ensure project documentation accurately reflects code changes.

## Scope

This skill applies to files changed in the current branch compared to `main` (or `origin/main`).
Identify changed files with: `git diff --name-only origin/main...HEAD`

## Step 1: Analyze Changes

Review what changed to determine documentation impact:

### Categorize Changes
- **New features**: Requires documentation of new functionality
- **API/interface changes**: Requires updated function/class docs
- **Architecture changes**: Requires updated design docs
- **Configuration changes**: Requires updated setup docs
- **Dependency changes**: Requires updated requirements docs
- **Algorithm changes**: Requires updated algorithm docs or comments
- **Bug fixes**: May require clarification of expected behavior

## Step 2: Docstring Updates

For each changed Python file, verify docstrings:

### Module Docstrings
- Top-level module docstring describes purpose
- Updated if module responsibility changed

### Function/Method Docstrings
- Public functions have clear docstrings
- Parameters and return values documented
- Complex algorithms have explanatory comments

```python
def tsp_route(bot_pos, item_targets, drop_off):
    """Find optimal pickup order using brute-force TSP.

    Args:
        bot_pos: Current bot position (x, y).
        item_targets: List of (item, adjacent_cell) tuples to visit.
        drop_off: Final delivery position (x, y).

    Returns:
        Reordered list of (item, cell) tuples in optimal pickup sequence.
    """
```

### Class Docstrings
- Purpose and usage described
- Key attributes documented if not obvious

## Step 3: README Updates

Review `README.md` for needed updates:

### Setup Instructions
- New dependencies or system requirements
- Changed installation steps
- New environment variables

### Usage Examples
- New commands or CLI options
- Changed workflow steps
- New features users should know about

### Configuration
- New configuration options
- Changed defaults

## Step 4: Architecture / Design Docs

If design documents exist (e.g., `OPTIMIZATION_PLAN.md`):
- Verify they reflect current implementation
- Mark completed items
- Update diagrams or descriptions
- Add new planned optimizations if discovered

## Step 5: Dependencies

If dependencies changed:
- Update `requirements.txt` or `pyproject.toml`
- Document why new dependencies were added
- Note any removed dependencies

## Step 6: Inline Documentation

Review code documentation in changed files:

### Algorithm Documentation
- Complex algorithms have comments explaining the approach
- Time/space complexity noted for critical functions
- Non-obvious optimizations explained

### Configuration Documentation
- Constants have comments explaining their purpose and tuning
- Magic numbers are named and documented

## Step 7: Commit Documentation Changes

Commit documentation updates separately from code changes:
- Use clear commit messages: "Update optimization plan with completed phases"
- Keep documentation commits focused

## Completion

Report:
- Documentation files updated
- New documentation created
- Docstrings added or updated
- Areas that may need future documentation work
- Any inconsistencies found between code and docs
