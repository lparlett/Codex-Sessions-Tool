# AGENTS.md

## Purpose

Defines Codex's expected behavior and project conventions for the
**Codex-Sessions-Tool** repository.
Goals: reproducibility, privacy, and clarity.

## Environment

* Python 3.12 (virtual env `.venv/`)
* SQLite database (`sqlite3`)
* Do not assume root/sudo access or system-level writes.

---

## Repository Structure

```bash
cli/                 # CLI entry points and orchestration
docs/                # Documentation and governance records
reports/             # Parsed and redacted transparency outputs
src/                 # Core implementation
  parsers/           # JSONL ingestion, validation, normalization
  models/            # Typed data structures for structured outputs
  services/          # Shared utilities (I/O, filtering, summarization)
tests/               # Pytest suites
  fixtures/          # Synthetic and sanitized samples, golden outputs
```

Input (Codex session logs) comes from a user-supplied path. The tool reads but does not store raw logs without explicit consent.

---

## Codex Sessions Log Files

Codex divides its JSONL session logs first by year, then month, and then day directories. An example of that is shown below. It demonstrates the nested directories and one log file for 10/30/2025. If multiple chat sessions occur, then more than one file will be in that same "day" folder.

```text
.codex/sessions/
  2025/
    09/
    10/
      30/
        rollout-2025-10-30T13-20-55-019a3623-0376-7d52-8c06-bc4b1bfed278.jsonl
```

On Windows this defaults to `C:\Users\<user>\.codex\sessions\2025\10\30\<file>.jsonl`.
On macOS and Linux the equivalent location is `~/.codex/sessions/2025/10/30/<file>.jsonl`.
If logs are copied elsewhere, preserve this hierarchy or update configuration so the tool can discover sessions predictably.

## Session Data Governance

* Treat all session logs as sensitive until sanitized; never commit raw `.jsonl` files.
* Persist derived reports only when redacted to the level agreed by the user; note any manual redactions in accompanying docs.
* Record the source path or identifiers only in local configuration files ignored by git (`.env`, `.codex_tool.ini`, etc.).
* Leave user-initiated redaction workflows configurable so future automation can hook in without code changes.

---

## Coding Standards

* Follow **PEP 8** for style, **PEP 484** for typing, **Google-style** for docstrings.
* Use modular, testable functions with clear naming.
* Header comment in each file: purpose, author (Codex + user), date, and related tests.
* Keep imports explicit and alphabetized.
* As often as practical, keep line length to 80.
* Favor clarity over brevity; avoid one-liners that obscure logic.

---

## Testing Conventions

* All tests use **pytest**.
* Test files named `test_<module>.py`.
* Fixtures stored in `/tests/fixtures/` with golden outputs for canonical parsing cases.
* Assertions preferred over print debugging.
* Coverage includes: happy-path parsing, malformed/truncated lines, and CLI smoke tests that validate exit codes and report generation.

---

## Documentation

* Use Sphinx-compatible reStructuredText docstrings.
* Update `/docs/schema_changes.md` for every schema modification.
* Each module added should include a short summary in `README.md`.

---

## Security-First Development Rules

Source: [StackHawk](https://www.stackhawk.com/blog/4-best-practices-for-ai-code-security-a-developers-guide/)

### Code Security Standards

* Always use parameterized queries - never string concatenation for database queries
* Implement proper input validation and sanitization for all user inputs
* Use secure authentication and authorization patterns
* Never hardcode secrets, API keys, or passwords in source code
* Implement proper error handling that doesn't expose sensitive information
* Follow OWASP Top 10 guidelines for web application security

### Dependency Management

* Only suggest well-maintained packages with recent updates
* Prefer packages with strong security track records
* Flag any dependencies that haven't been updated in 12+ months
* Always check for known vulnerabilities before suggesting packages

### Code Review Requirements

* Generate TODO comments for any code that needs security review
* Add inline comments explaining security-relevant decisions
* Flag any code that handles sensitive data for manual review
* Suggest security test cases for authentication and authorization logic

### Error Handling

* Implement fail-secure patterns (deny by default)
* Log security events appropriately without exposing sensitive data
* Use structured error responses that don't leak implementation details

---

## AI Disclosure

* Generated code must include a brief comment noting that it was AI-assisted.
* Do not inject this comment into private data or schema dumps.

---

## Communication & Tone

* Provide concise explanations of design choices before generating code.
* Summarize outputs instead of printing large data blocks.
* When uncertain, ask clarifying questions rather than guessing.
* Maintain a factual, explanatory tone.

---

## Versioning & Branching Guidelines

### Automation rules

* Never auto-commit, merge, or push without explicit human confirmation
* Always perform `git pull --rebase` before committing to avoid merge noise
* If conflicts occur, pause for human review -- do not attempt auto-resolution
* Do not modify `.gitignore`, `.gitattributes`, or `.gitmodules` without approval

### Documentation hints

* Each release should have a matching entry in `CHANGELOG.md`
* Include the related issue or PR number in the commit body when available
* Treat commits as part of the project's provenance record
* Include AI-assisted code attribution in the commit body, referencing the prompt(s) and model used

---

Last updated: 2025-10-30
