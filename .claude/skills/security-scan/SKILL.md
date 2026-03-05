---
name: security-scan
description: Run security scans with bandit and pip-audit. Use when the user asks to check for security issues, run security scans, or audit dependencies.
---

# Security Scan Skill

Scan for security vulnerabilities in code and dependencies.

## Scope

This skill scans the entire Python project for security issues.
It is not limited to changed files since security vulnerabilities can exist in any part of the codebase.

## Step 1: Bandit Static Analysis

Run bandit to scan for common security issues in Python code:

```bash
bandit -r . -f json
# or for readable output:
bandit -r . -ll
```

If bandit is not installed: `pip install bandit`

### Common Issues to Fix

**Hardcoded Passwords/Secrets**
- Move to environment variables or config files
- Use `python-dotenv` or `os.environ`

**Unsafe Deserialization**
- Avoid `pickle.loads()` on untrusted data
- Prefer `json.loads()` for data exchange

**Command Injection**
- Avoid `os.system()`, `subprocess.call(shell=True)` with user input
- Use `subprocess.run()` with list arguments

**SQL Injection**
- Use parameterized queries, never string formatting
- Use ORM query builders

**Insecure Temporary Files**
- Use `tempfile.mkstemp()` or `tempfile.TemporaryDirectory()`
- Avoid predictable temp file names

**Unsafe YAML Loading**
- Use `yaml.safe_load()` instead of `yaml.load()`

### Handling Warnings

For each warning:
1. Understand the vulnerability
2. Fix the code properly
3. Do NOT use `# nosec` comments unless absolutely necessary
4. If a false positive, document why in a comment

## Step 2: Dependency Audit

Check for known vulnerabilities in Python dependencies:

```bash
# pip-audit (preferred)
pip-audit

# or safety
safety check
```

If not installed: `pip install pip-audit` or `pip install safety`

### Handling Vulnerable Dependencies

**If a patched version exists:**
1. Update in `requirements.txt` / `pyproject.toml`
2. Run `pip install -U <package>`
3. Run tests to verify compatibility

**If no patch is available:**
1. Check if the vulnerability affects your usage
2. Consider alternative packages
3. Document the risk if you must continue using it
4. Monitor for updates

## Step 3: Additional Checks

### Check for Hardcoded Secrets
Search for potential secrets in code:
- API keys, tokens, passwords
- Private keys, connection strings
- AWS credentials, database URLs

These should be in environment variables or `.env` files (which are `.gitignore`d).

### Check for Insecure Dependencies
Review packages that:
- Are unmaintained (no updates in 2+ years)
- Have open security issues
- Have low download counts (potential supply chain risk)

### Check .gitignore
Ensure sensitive files are excluded:
- `.env`, `.env.*`
- `*.pem`, `*.key`
- `credentials.*`, `secrets.*`

## Step 4: Verify Clean

Run all scans again to confirm all issues are resolved:

```bash
bandit -r . -ll
pip-audit
```

## Completion

Report:
- Number of bandit warnings found and fixed
- Number of vulnerable dependencies found and updated
- Any remaining issues that need attention
- Recommendations for ongoing security hygiene
