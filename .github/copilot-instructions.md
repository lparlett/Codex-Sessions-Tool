# Codex Sessions Tool - AI Contribution Guide

This guide helps AI agents understand the key patterns and workflows of the Codex Sessions Tool codebase. The tool ingests AI session logs (JSONL) into SQLite for transparency reporting.

## Core Architecture

```
cli/ → src/parsers/ → src/services/ → SQLite
[entry]  [normalize]   [persist]      [storage]
```

Key flows:
1. CLI validates config & finds session files
2. Parser loads JSONL and groups by user messages
3. Services validate/sanitize content and persist to SQLite
4. Raw JSON preserved alongside structured data

## Critical Patterns

### Event Processing Pipeline
```python
# Exemplified in src/services/ingest.py
raw_events → validate → sanitize → group → process → persist
```
- Events processed in batches (1000 default) for memory safety
- All events validated against schema before processing
- Sensitive data detected and redacted during sanitization
- Events grouped by user message for context preservation

### Database Interactions
- Validation occurs via `src/services/validation.py`, ensuring each event has structured payloads before hitting SQLite.
- Sensitive fields are redacted in-memory by `src/services/sanitization.py`; sanitized objects are passed to parameterized SQL writers.
- Database utilities (`src/parsers/handlers/db_utils.py`) rely solely on parameterized statements; raw SQL never interpolates user data.
- Always use parameterized queries (see `src/parsers/handlers/db_utils.py`)
- Tables have cascading foreign keys from files → prompts → messages
- Raw JSON stored in *_json columns for audit/reprocessing
- Each ingestion runs in a single transaction

### Error Handling
```python
# Pattern from src/services/ingest.py
class ErrorSeverity(Enum):
    WARNING = auto()   # Continue processing
    ERROR = auto()     # Skip current item
    CRITICAL = auto()  # Stop processing file
```
All errors must:
- Be logged with severity and context
- Not expose sensitive information
- Be included in ingestion summaries

## Development Workflow

### Environment Setup
```bash
python -m venv .venv
. .venv/bin/activate  # or .venv\Scripts\activate on Windows
cp user/config.example.toml user/config.toml
# Edit config.toml to set sessions_root path
```
- Optional tuning lives under `[ingest]`; adjust `batch_size` to control how many
  events are prepared per chunk (default 1000).

### Common Commands
```bash
# Ingest first session with debug output
python -m cli.ingest_session --debug

# View grouped events from earliest session
python -m cli.group_session -o reports/session.txt
```

### Testing (Planned)
- Tests will use pytest with fixtures in tests/fixtures/
- Synthetic JSONL files will provide canonical test cases
- SQLite :memory: mode used for integration tests

## Key Files

- `src/services/validation.py` - Event schema validation
- `src/services/sanitization.py` - Secret detection patterns
- `src/services/database.py` - SQLite schema definition
- `src/parsers/session_parser.py` - JSONL parsing/grouping
- `cli/ingest_session.py` - Main ingestion workflow

## Conventions

1. Data Safety
   - All user data treated as sensitive until sanitized
   - No raw JSONL files committed to repo
   - Config with paths stays in user/ (gitignored)

2. Code Style
   - PEP 8 and 80-char lines where practical
   - Type hints required (PEP 484)
   - Google-style docstrings
   - AI assistance noted in file headers

3. Error Classification
   ```python
   # All errors should use structured format:
   ProcessingError(
       severity=ErrorSeverity.WARNING,
       code="invalid_event",
       message="Failed to validate event schema",
       file_path=session_file,
       line_number=index
   )
   ```
