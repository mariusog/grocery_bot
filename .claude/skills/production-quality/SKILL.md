---
name: production-quality
description: Brings code up to production quality level by orchestrating lint, refactor, test-coverage, security-scan, code-review, and update-documentation skills. Use when the user asks to clean up code, improve code quality, prepare code for production, or run the production quality routine.
---

# Production Quality Code Routine

Orchestrates multiple quality skills to bring all changed files up to production quality level.

## Scope

This routine applies to all files changed in the current branch compared to `main` (or `origin/main`).
Identify changed files with: `git diff --name-only origin/main...HEAD`

### File Type Considerations

| File Type | Lint | Refactor | Test Coverage | Security | Code Review |
|-----------|------|----------|---------------|----------|-------------|
| Python (`.py`) | ruff | Yes | pytest | bandit | Yes |
| Notebooks (`.ipynb`) | ruff/nbqa | Yes | Verify outputs | Review | Yes |
| Config (`.toml`, `.yaml`, `.json`) | N/A | N/A | Integration tests | Review secrets | Verify correctness |
| Docker/CI | N/A | N/A | Run pipeline | Review exposure | Verify correctness |
| Markdown (`.md`) | N/A | N/A | N/A | N/A | Verify accuracy |

## Step 1: Baseline Test Run

Run the `test-coverage` skill to ensure we start green:
- Identifies all relevant test files for changed code
- Runs baseline tests
- **If tests fail, STOP** — do not proceed with quality improvements on broken code

```bash
pytest -v
```

## Step 2: Lint Cleanup

Run the `lint` skill to fix code style issues:
- ruff for linting and formatting
- mypy for type checking (if configured)
- Do NOT disable any rules

## Step 3: Refactor for Clarity

Run the `refactor` skill to improve code structure:
- Replace conditionals with dict lookups where appropriate
- Use early returns and guard clauses
- Extract magic numbers and strings to constants
- Remove unnecessary comments

## Step 4: Test Coverage Check

Run the `test-coverage` skill again to:
- Verify all new public functions have tests
- Check edge cases and error paths
- Add missing tests if coverage is insufficient

## Step 5: Security Scan

Run the `security-scan` skill to check for vulnerabilities:
- bandit static analysis for Python security issues
- pip-audit for vulnerable dependencies
- Fix any issues found

## Step 6: Commit Changes

Commit the work in small, structured commits:
- One logical change per commit
- Use short, single-sentence commit messages in present tense
- No mention of Claude Code or author attribution
- Examples: "Extract BFS cache to module-level dict", "Replace conditionals with lookup dict"

## Step 7: Code Review Loop

Run the `code-review` skill iteratively:
- Review for SOLID violations, Python best practices, performance issues
- Fix the most critical issues found
- Commit each fix separately with clear messages
- Run tests after each fix
- Repeat until no critical issues remain

## Step 8: Update Documentation

Run the `update-documentation` skill to ensure docs are current:
- Update README if user-facing behavior changed
- Update architecture docs if structural changes were made
- Update docstrings for changed public APIs

## Step 9: Final Checks

Run all quality checks one final time:

```bash
ruff check .                    # verify no style issues
ruff format --check .           # verify formatting
pytest -v                       # verify all tests pass
bandit -r . -ll                 # verify no security issues
```

Do NOT disable any rules or remove any test functions.

## Step 10: Skill Self-Improvement

Review this run and improve the skills themselves:

### Identify Gaps
- Were any steps unclear or incomplete?
- Did you discover checks that should be added?
- Were there quality issues the skills didn't catch?

### Update Skills
If improvements are identified:
1. Update the relevant skill file(s) in `.claude/skills/`
2. Keep changes focused and actionable
3. Add concrete examples where helpful
4. Commit with message: "Improve [skill-name] skill based on production quality run"

### Skip If No Improvements
If the run was smooth and no gaps were found, skip this step.

## Completion

Summarize:
- Number of commits made
- Key improvements made (from each skill)
- Test coverage status
- Security scan results
- Documentation updates made
- Skill improvements made (if any)
- Any remaining non-critical items for future consideration
