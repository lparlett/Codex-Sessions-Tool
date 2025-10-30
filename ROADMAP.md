# Codex Sessions Tool Roadmap

This roadmap outlines the path to a viable **v1.0.0** release and sketches the extensions that follow.

---

## Phase 0: Foundations (in progress)

- Ingest Codex JSONL sessions into normalized SQLite tables (`files`, `sessions`, `prompts`, `token_messages`, `turn_context_messages`, `agent_reasoning_messages`, `function_plan_messages`, `function_calls`).
- Capture raw JSON alongside structured rows to enable future reprocessing and audits.
- CLI utilities for grouping events (`cli.group_session`) and ingesting sessions (`cli.ingest_session` with limit/debug/verbose modes).

---

## Phase 1: Viable v1.0.0 (core transparency export)

### 1. Configuration & Schema Hardening

- [ ] Add schema migration tooling (sqlite-utils migrations or Alembic) to evolve the database without wiping data.
- [ ] Expose DB path and output directories in `user/config.toml`; validate paths on startup.
- [ ] Implement automated tests for ingestion helpers (`group_by_user_messages`, `_parse_prompt_message`, `_insert_function_call`).

### 2. Redaction & Policy Baseline

- [ ] Introduce a `redactions` table with prompt-level and field-level overrides (replacement text, actor, timestamp, reason).
- [ ] Allow automatic redaction rules (e.g., regex patterns, `[redact ...]` markers) configurable via YAML/JSON.
- [ ] Provide CLI commands to list, add, and remove redactions; ensure exports apply redactions by default.

### 3. Reporting Pipeline

- [ ] Build a reporting CLI (`codex-tool report`) that can export:
  - Prompts only (chronological).
  - Prompts + agent reasoning/actions.
  - Token usage summaries.
  - All exports in Markdown and CSV.
- [ ] Allow filtering by date range, repo/workspace, or session id.
- [ ] Include transparency metadata (e.g., “entries redacted by …”).

### 4. User Interface

- [ ] Implement a local review UI (Streamlit prototype) with:
  - Session browser (list by date/repo).
  - Prompt detail view (context, agent actions).
  - Redaction controls (toggle/hide text, add rationale).
- [ ] Persist UI actions back into the SQLite redactions table.
- [ ] Provide an “Export” button that mirrors the reporting CLI.

### 5. Distribution & Documentation

- [ ] Package the tool via `pipx` (or a zipapp) so users can install and run from a single command.
- [ ] Write quick-start docs covering config, ingest, review, redaction, export.
- [ ] Add governance notes explaining data ownership, privacy, and audit trails.

**Exit criteria for v1.0.0:**  

Users can ingest all sessions, review prompts/actions, apply redactions through CLI or UI, and export sanitized reports suitable for repo transparency.

---

## Phase 2: Quality & Collaboration Enhancements

- Add tagging: allow prompts and sessions to be labeled (e.g., repo names, project themes). Provide filters in UI/CLI.
- Introduce notes/disposition columns (e.g., “followed”, “ignored”, “needs review”).
- Track redaction history (versioning, undo, audit logs).
- Offer diff-based preview: raw vs redacted side-by-side before publishing.
- Integrate token cost analytics (aggregate token_count events, estimate cost).
- Provide REST/GraphQL API (FastAPI) so other tools (VS Code extensions, dashboards) can consume the data.

---

## Phase 3: Integrations & Publishing

- Build a VS Code extension that surfaces prompts/actions inline and lets users redact from the editor.
- Add GitHub Action / CLI support to generate transparency reports during CI (using redaction rules committed to repo).
- Support multi-user workflows: per-user redaction namespaces, shared databases, or sync with central datastore.
- Implement optional cloud sync (S3/SQLite over HTTP) for teams needing centralized storage.
- Explore transformer-based summarization to provide “agent action summaries” per prompt.

---

## Phase 4: Advanced Features (vision)

- Plug into issue trackers: auto-link prompts/actions to Jira/GitHub issues.
- Offer PDF/HTML interactive transparency dashboards (Plotly Dash, Superset integration).
- Anomaly detection: flag prompts where agent actions touched sensitive repositories or made large changes.
- Provide compliance exports (e.g., SOC2/ISO templates) compiling AI usage records.

---

## Ongoing Tasks

- Maintain comprehensive unit/integration tests; add sample fixtures with synthetic logs.
- Monitor schema changes and keep `AGENTS.md` / docs updated.
- Collect user feedback from early adopters to refine UI/UX, redaction flows, and reporting formats.

---

**Next checkpoint:** Finish Phase 1 backlog items, ship v1.0.0, gather feedback from internal projects, then prioritize Phase 2 initiatives based on usage patterns.
