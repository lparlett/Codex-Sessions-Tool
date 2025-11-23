# AGENTS.md

## Purpose

Defines Codex's expected behavior and project conventions for the
**Codex-Sessions-Tool** repository. Goals: reproducibility, privacy, and
clarity.

## Environment

* Python 3.12 (virtual env `.venv/`)
* SQLite database (`sqlite3`)
* Do not assume root/sudo access or system-level writes.

---

## Repository Structure

```bash
cli/                  # CLI entry points (ingest_session.py, group_session.py)
docs/                 # Documentation and governance records
reports/              # Parsed and redacted transparency outputs
src/
  agents/             # Agent-specific models (e.g., codex action/message/config)
  core/               # Shared base types, interfaces, and data containers
  parsers/            # Session discovery and grouping helpers
  services/           # Config loading, ingest pipeline, validation, sanitization
tests/                # Pytest suites and fixtures
  fixtures/           # Synthetic/sanitized sample session logs
user/                 # User-provided configuration (gitignored)
```

Input (Codex session logs) comes from a user-supplied path. The tool reads
but does not store raw logs without explicit consent.

---

## Core Architecture & Workflow

```txt
cli/ -> src/parsers/ -> src/services/ -> SQLite
[entry] [normalize]   [persist]        [storage]
```

Key flows:

1. CLI validates config and finds session files.
2. Parser loads JSONL and groups by user messages.
3. Services validate/sanitize content and persist to SQLite.
4. Raw JSON is preserved alongside structured data.

Event processing pipeline (see `src/services/ingest.py`):

```txt
raw_events -> validate -> sanitize -> group -> process -> persist
```

Database interactions:

* Validation occurs via `src/services/validation.py` before any SQLite writes.
* Sensitive fields are redacted in memory by `src/services/sanitization.py`.
* Writers (for example `src/parsers/handlers/db_utils.py`) must use
  parameterized SQL only.
* Tables use cascading foreign keys from files -> prompts -> messages.
* Raw JSON is stored in *_json columns for audit/reprocessing.
* Each ingestion runs in a single transaction.

Error handling pattern:

```python
class ErrorSeverity(Enum):
    WARNING = auto()   # Continue processing
    ERROR = auto()     # Skip current item
    CRITICAL = auto()  # Stop processing file
```

All errors must be logged with severity and context, avoid leaking sensitive
data, and be included in ingestion summaries.

---

## Codex Sessions Log Files

Codex divides its JSONL session logs first by year, then month, and then day
directories. An example of that is shown below. It demonstrates the nested
directories and one log file for 10/30/2025. If multiple chat sessions occur,
then more than one file will be in that same "day" folder.

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
If logs are copied elsewhere, preserve this hierarchy or update configuration
so the tool can discover sessions predictably.

## Session Data Governance

* Treat all session logs as sensitive until sanitized; never commit raw
  `.jsonl` files.
* Persist derived reports only when redacted to the level agreed by the user;
  note any manual redactions in accompanying docs.
* Record the source path or identifiers only in local configuration files
  ignored by git (`.env`, `.codex_tool.ini`, etc.).
* Leave user-initiated redaction workflows configurable so future automation
  can hook in without code changes.

---

## Development Workflow

Environment setup:

```bash
python -m venv .venv
. .venv/bin/activate  # or .venv\Scripts\activate on Windows
cp user/config.example.toml user/config.toml
# Edit config.toml to set sessions_root path
```

Optional tuning lives under `[ingest]`; adjust `batch_size` to control how
many events are prepared per chunk (default 1000).

Common commands:

```bash
# Ingest first session with debug output
python -m cli.ingest_session --debug

# View grouped events from earliest session
python -m cli.group_session -o reports/session.txt
```

---

## Coding Standards

* Follow **PEP 8** for style, **PEP 484** for typing, and Google-style
  docstrings.
* Use modular, testable functions with clear naming.
* Header comment in each file: purpose, author (Codex + user), date, and
  related tests.
* Keep imports explicit and alphabetized; keep lines near 80 characters.
* Favor clarity over brevity; avoid one-liners that obscure logic.
* All code must pass linting with `flake8` and `mypy` and be formatted with
  `black`.

---

## Testing Conventions

* All tests use **pytest**; test files named `test_<module>.py`.
* Fixtures stored in `/tests/fixtures/` with golden outputs for canonical
  parsing cases.
* Avoid bare `assert` statements; use unit test frameworks' assertion helpers instead of print debugging.
* Coverage includes happy-path parsing, malformed/truncated lines, and CLI
  smoke tests that validate exit codes and report generation.
* SQLite `:memory:` mode is used for integration tests.

---

## Documentation

* Use Sphinx-compatible reStructuredText docstrings.
* Update `/docs/schema_changes.md` for every schema modification.
* Each module added should include a short summary in `README.md`.

---

## Security-First Development Rules

Source: [StackHawk](https://www.stackhawk.com/blog/4-best-practices-for-ai-code-security-a-developers-guide/)

### Code Security Standards

* Always use parameterized queries; never build SQL via string concatenation.
* Implement proper input validation and sanitization for all user inputs.
* Use secure authentication and authorization patterns.
* Never hardcode secrets, API keys, or passwords in source code.
* Implement proper error handling that does not expose sensitive information.
* Follow OWASP Top 10 guidelines for web application security.

### Dependency Management

* Only suggest well-maintained packages with recent updates.
* Prefer packages with strong security track records.
* Flag any dependencies that have not been updated in 12+ months.
* Always check for known vulnerabilities before suggesting packages.

### Code Review Requirements

* Generate TODO comments for any code that needs security review.
* Add inline comments explaining security-relevant decisions.
* Flag any code that handles sensitive data for manual review.
* Suggest security test cases for authentication and authorization logic.

### Error Handling

* Implement fail-secure patterns (deny by default).
* Log security events appropriately without exposing sensitive data.
* Use structured error responses that do not leak implementation details.
* When representing errors in code, prefer a structured format such as:

```python
ProcessingError(
    severity=ErrorSeverity.WARNING,
    code="invalid_event",
    message="Failed to validate event schema",
    file_path=session_file,
    line_number=index,
)
```

---

## AI Disclosure

* Generated code must include a brief comment noting that it was AI-assisted
  (for example, in the file header).
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

* Never auto-commit, merge, or push without explicit human confirmation.
* Always perform `git pull --rebase` before committing to avoid merge noise.
* If conflicts occur, pause for human review -- do not attempt auto-resolution.
* Do not modify `.gitignore`, `.gitattributes`, or `.gitmodules` without
  approval.

### Documentation hints

* Each release should have a matching entry in `CHANGELOG.md`.
* Include the related issue or PR number in the commit body when available.
* Treat commits as part of the project's provenance record.
* Include AI-assisted code attribution in the commit body, referencing the
  prompt(s) and model used.

---

Last updated: 2025-11-23
