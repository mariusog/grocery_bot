---
name: lint
description: Run ruff, mypy, and formatting checks to fix code style and quality issues. Use when the user asks to lint code, fix style issues, or run code quality checks.
---

# Lint Skill

Fix code style and quality issues using ruff (linting + formatting) and mypy (type checking).

## Scope

This skill applies to files changed in the current branch compared to `main` (or `origin/main`).
Identify changed files with: `git diff --name-only origin/main...HEAD`

## Step 1: Identify Changed Files

Categorize changed files:
- **Python files**: `*.py` files
- **Notebooks**: `*.ipynb` files
- **Config files**: `pyproject.toml`, `setup.cfg`, etc.
- Skip linting for file types that have no changes

## Step 2: Ruff Linting (Python files)

If Python files were changed:

```bash
# Check for issues
ruff check <changed files>

# Auto-fix what's possible
ruff check --fix <changed files>

# Format code
ruff format <changed files>
```

If ruff is not installed, fall back to:
```bash
# flake8 for linting
flake8 <changed files>

# black for formatting
black <changed files>

# isort for import sorting
isort <changed files>
```

### Common Ruff Rules to Fix
- **F** (Pyflakes): unused imports, undefined names
- **E/W** (pycodestyle): whitespace, line length, indentation
- **I** (isort): import ordering
- **UP** (pyupgrade): modernize Python syntax
- **B** (flake8-bugbear): common bugs and design issues
- **SIM** (flake8-simplify): simplifiable code

### Rules to Respect
- Do NOT add `# noqa` comments to suppress warnings
- Do NOT disable any linting rules
- Do NOT remove any test cases or test functions

## Step 3: Type Checking (if configured)

If `mypy` or type checking is configured:

```bash
mypy <changed files>
```

Fix type errors properly:
- Add missing type annotations
- Fix incompatible types
- Do NOT use `# type: ignore` unless truly necessary (document why)

## Step 4: Verify Clean

Run linters one final time to confirm all issues are resolved:

```bash
ruff check <changed files>
ruff format --check <changed files>
```

## Completion

Report:
- Number of files linted
- Number of offenses fixed
- Any remaining issues that need manual attention
