---
name: dependency-management
description: Manages project dependencies, virtual environments, lock files, and version pinning. Language-neutral principles with multi-language examples. Use when setting up environments, adding dependencies, auditing packages, or when user mentions dependencies, packages, virtual environment, lock file, or version pinning.
---

# Dependency Management

## Core Principles

1. **Isolate environments** -- never install into the system/global interpreter
2. **Pin versions** -- reproducible builds require exact versions
3. **Lock files in version control** -- the lock file IS your reproducible build
4. **Separate dev from prod** -- test/lint tools don't ship to production
5. **Audit regularly** -- known vulnerabilities in dependencies are your vulnerabilities
6. **Minimal dependencies** -- every dependency is a maintenance burden and attack surface

## Language-Specific Setup

### Python

#### Environment Isolation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# Or with uv (faster)
uv venv
source .venv/bin/activate
```

#### Dependency Files

| File | Purpose | In Git? |
|------|---------|---------|
| `pyproject.toml` | Declared dependencies (ranges) | Yes |
| `requirements.txt` | Pinned versions (lock) | Yes |
| `requirements-dev.txt` | Dev-only deps (test, lint) | Yes |
| `.venv/` | Installed packages | No |

#### Pinning Versions

```bash
# Generate locked requirements from pyproject.toml
pip-compile pyproject.toml -o requirements.txt
pip-compile pyproject.toml --extra dev -o requirements-dev.txt

# Or with uv
uv pip compile pyproject.toml -o requirements.txt

# Install from lock file (reproducible)
pip install -r requirements.txt
```

#### pyproject.toml Pattern

```toml
[project]
name = "myproject"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "numpy>=1.24,<2",
    "requests>=2.28,<3",
]

[project.optional-dependencies]
dev = [
    "pytest>=7",
    "ruff>=0.1",
    "mypy>=1.5",
    "bandit>=1.7",
    "pip-audit>=2.6",
]
```

### TypeScript / Node.js

```bash
# Use a version manager
nvm use 20  # or fnm use 20

# Install from lock file (reproducible)
npm ci          # Not `npm install` (which updates lock file)
# Or
yarn install --frozen-lockfile
# Or
pnpm install --frozen-lockfile
```

| File | Purpose | In Git? |
|------|---------|---------|
| `package.json` | Declared dependencies | Yes |
| `package-lock.json` / `yarn.lock` / `pnpm-lock.yaml` | Pinned versions | Yes |
| `node_modules/` | Installed packages | No |

### Go

```bash
# Dependencies managed via go.mod automatically
go mod tidy    # Add missing, remove unused
go mod verify  # Verify checksums
```

| File | Purpose | In Git? |
|------|---------|---------|
| `go.mod` | Declared dependencies | Yes |
| `go.sum` | Checksums (lock) | Yes |

### Rust

```bash
cargo build    # Generates Cargo.lock if missing
cargo update   # Update within semver ranges
```

| File | Purpose | In Git? |
|------|---------|---------|
| `Cargo.toml` | Declared dependencies | Yes |
| `Cargo.lock` | Pinned versions | Yes (for binaries), No (for libraries) |

## Adding a New Dependency

Follow this checklist every time:

1. **Do you actually need it?** Can the standard library do this in <20 lines?
2. **Check quality**: GitHub stars, last commit date, open issue count, maintenance status
3. **Check security**: Run the audit tool after adding
4. **Pin the version range**: Use compatible ranges, not `*` or `latest`
5. **Update the lock file**: Commit the updated lock file
6. **Document why**: If the dependency isn't obvious, add a comment

```bash
# Python
pip install "newpackage>=1.2,<2"
pip freeze > requirements.txt  # Or use pip-compile
pip-audit  # Check for known vulnerabilities

# TypeScript
npm install newpackage@^1.2
npm audit

# Go
go get newpackage@v1.2
govulncheck ./...

# Rust
cargo add newpackage@1.2
cargo audit
```

## Security Auditing

Run these regularly (in CI and locally):

```bash
# Python
pip-audit --strict
bandit -r src/ -ll

# TypeScript
npm audit --audit-level=moderate

# Go
govulncheck ./...

# Rust
cargo audit
```

## Dependency Update Strategy

| Frequency | Action |
|-----------|--------|
| Weekly | Run audit tool, fix critical vulnerabilities |
| Monthly | Update patch versions (bug fixes) |
| Quarterly | Evaluate minor version updates |
| As needed | Major version updates (plan migration) |

### Safe Update Workflow

```bash
# 1. Create a branch
git checkout -b deps/update-monthly

# 2. Update dependencies
pip-compile --upgrade pyproject.toml -o requirements.txt  # Python
npm update                                                  # TypeScript
go get -u ./...                                            # Go
cargo update                                               # Rust

# 3. Run full test suite
<test command from Tooling table>

# 4. Run security audit
<security scan command from Tooling table>

# 5. If tests pass, commit and PR
```

## Common Problems

| Problem | Cause | Fix |
|---------|-------|-----|
| "Works on my machine" | Different dependency versions | Use lock file + `pip install -r` / `npm ci` |
| Install modifies lock file | Using `pip install` / `npm install` | Use `pip install -r requirements.txt` / `npm ci` |
| Conflicting versions | Incompatible version ranges | Check constraints, find compatible range |
| Vulnerability in transitive dep | Indirect dependency has CVE | Update parent dep, or pin transitive dep |
| Slow installs | Large dependency tree | Audit for unused deps, use `uv` (Python) or `pnpm` (Node) |

## Checklist

- [ ] Environment isolation set up (venv, nvm, etc.)
- [ ] Lock file committed to version control
- [ ] Dev dependencies separated from production
- [ ] All versions pinned with compatible ranges (not `*`)
- [ ] Security audit runs in CI pipeline
- [ ] `.gitignore` excludes installed packages (`.venv/`, `node_modules/`)
- [ ] New dependency checklist followed for every addition
- [ ] Lock file regenerated after any dependency change
