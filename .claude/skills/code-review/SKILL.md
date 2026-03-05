---
name: code-review
description: Perform a thorough code review looking for SOLID violations, Python best practices, performance issues, and code smells. Use when the user asks to review code, check for issues, or improve code quality.
---

# Code Review Skill

Perform a comprehensive code review on changed files, iterating until no critical issues remain.

## Scope

This skill applies to files changed in the current branch compared to `main` (or `origin/main`).
Identify changed files with: `git diff --name-only origin/main...HEAD`

## Review Checklist

Review the code as a top 0.01% Python developer. For each changed file, check for:

### SOLID Principles

**Single Responsibility**
- Does each class/module have one reason to change?
- Are functions focused on a single task?

**Open/Closed**
- Is the code open for extension but closed for modification?
- Can behavior be extended without changing existing code?

**Liskov Substitution**
- Can subclasses be used interchangeably with their base classes?
- Do overridden methods maintain expected behavior?

**Interface Segregation**
- Are interfaces (ABCs/Protocols) focused and minimal?
- Do classes depend only on methods they use?

**Dependency Inversion**
- Do high-level modules depend on abstractions?
- Are dependencies injected rather than hardcoded?

### Python Best Practices

**Type Hints**
- Public functions have type annotations
- Complex return types are clearly annotated
- Use `typing` module appropriately (Optional, Union, TypeAlias, etc.)

**Data Structures**
- Appropriate use of dataclasses, NamedTuples, or TypedDicts
- Proper use of collections (defaultdict, Counter, deque, etc.)
- Immutable structures where mutation isn't needed (tuples, frozensets)

**Idioms**
- Pythonic patterns (list comprehensions, generators, unpacking)
- Context managers for resource handling
- Proper use of `__init__`, `__repr__`, `__eq__` etc.
- f-strings over `.format()` or `%` formatting

**Module Organization**
- Logical grouping of functions and classes
- Clear public API (use `__all__` or `_` prefix for private)
- Avoid circular imports

### Performance Issues

**Algorithmic Complexity**
- Unnecessary nested loops (O(n²) when O(n) is possible)
- Repeated work that could be cached or precomputed
- Using lists where sets/dicts would give O(1) lookup

**Memory Usage**
- Generators instead of lists for large sequences
- Avoid unnecessary copies of large data structures
- Use `__slots__` for classes with many instances

**Data Science Specifics**
- Vectorized operations over Python loops (numpy/pandas)
- Appropriate use of `.apply()` vs vectorized alternatives
- Avoid repeated DataFrame copies

### Code Smells

**Long Functions**
- Functions longer than 30 lines should be reviewed
- Consider extracting smaller, focused functions

**Long Parameter Lists**
- More than 4-5 parameters suggests a design issue
- Consider using dataclasses, TypedDicts, or keyword arguments

**Feature Envy**
- Functions that use another object's data extensively
- Consider moving the function to the appropriate class/module

**Primitive Obsession**
- Using raw dicts where dataclasses would be clearer
- Magic strings/numbers instead of enums or constants

**Duplicate Code**
- Similar logic in multiple places
- Extract to shared functions or modules

### Error Handling

**System Boundaries**
- External API calls wrapped in proper error handling
- User input validated appropriately
- File operations handle missing files (pathlib)

**Graceful Degradation**
- Reasonable fallback behavior
- Informative error messages
- Proper logging of errors (`logging` module, not `print`)

### Testing Patterns

- Tests use pytest fixtures and parametrize
- Mocks are scoped appropriately
- Test names describe behavior, not implementation

## Review Loop Process

1. **Review**: Read through all changed files
2. **Identify**: List critical issues found
3. **Fix**: Address the most critical issue
4. **Test**: Run tests to verify no regressions
5. **Commit**: Commit the fix with a clear message
6. **Repeat**: Continue until no critical issues remain

### Issue Priority

**Critical** (must fix):
- Security vulnerabilities
- Data integrity issues
- Algorithmic correctness bugs
- Missing error handling at system boundaries

**Major** (should fix):
- SOLID violations that impact maintainability
- Performance issues in hot paths
- Missing type hints on public APIs

**Minor** (nice to fix):
- Style inconsistencies (if not caught by linter)
- Minor refactoring opportunities
- Documentation improvements

## Completion

Report:
- Number of issues found by category
- Number of issues fixed
- Any remaining items for future consideration
- Summary of key improvements made
