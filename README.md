# AI Log Trail
<!-- markdownlint-disable MD042 -->
[![Status](https://img.shields.io/badge/status-experimental-blueviolet)](#)
[![Version](https://img.shields.io/badge/version-0.1.0--dev-orange)](#)
[![Python](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](#)
![Codecov](https://img.shields.io/codecov/c/github/lparlett/ai-log-trail?logo=codecov&logoColor=%23F01F7A)
<!-- markdownlint-enable MD042 -->
> **Universal AI assistance logging with transparency.**  
> A flexible framework for capturing, analyzing, and sharing AI agent interactions while maintaining privacy and auditability. Supporting multiple AI agents and workflows, this tool helps organizations track and understand their AI usage patterns.

---

## Why this exists

Codex (and other AI coding tools) produce rich session logs, but they’re hard to read and even harder to share responsibly. The Codex Sessions Tool ingests `*.jsonl` session data, normalizes it into SQLite, and generates human-friendly reports that highlight:

- User prompts and the agent responses/actions.
- Token usage and cost indicators.
- Function calls, reasoning trails, and decision history.
- Redactions applied to sensitive content so transparency doesn’t compromise privacy.

The goal is a workflow where AI-assisted coding can be audited, explained, and optionally published in repositories or release notes.

---

## Current capabilities

- **Structured ingest** – Parse Codex session directories into tables (`files`, `sessions`, `prompts`, `token_messages`, `turn_context_messages`, `agent_reasoning_messages`, `function_plan_messages`, `function_calls`) with raw JSON preserved.
- **CLI utilities**
  - `python -m cli.group_session` groups events under each prompt for quick console or file review and writes to `[outputs].reports_dir` by default.
  - `python -m cli.ingest_session` ingests one or many sessions into SQLite with `--limit`, `--debug`, and `--verbose` modes using the configured database path.
- 🗺️ **Governance docs** – `AGENTS.md` sets behavioral guardrails; `ROADMAP.md` tracks milestones through v1.0.0 and beyond.
- 🧩 **Config scaffolding** – `user/config.example.toml` seeds per-user setup; actual secrets stay local via `.gitignore`.
- 📦 **Migration docs** – `docs/migration.md` explains SQLite → Postgres migration, dry-run, and rollback steps.

---

## Getting started

> Requires Python 3.12+

1. **Clone & configure**

   ```bash
   git clone <repo-url>
   cd Codex-Sessions-Tool
   cp user/config.example.toml user/config.toml
   # edit user/config.toml to set:
   #   [sessions].root -> Codex/Copilot logs directory
   #   [ingest].db_path -> SQLite destination
   #   [outputs].reports_dir -> where grouped reports should be written
   ```

   Optional tuning: set `[ingest].batch_size` in `user/config.toml` if you want a
   larger or smaller event batch during ingest (default is 1000).

2. **Ingest a sample**

   ```bash
   python -m cli.ingest_session --debug
   ```

   This ingests the first two sessions, logs verbose output, and writes to `[ingest].db_path`.
3. **Explore prompts**

   ```bash
   python -m cli.group_session
   ```

   Generates a grouped text report for the earliest session, stored under `[outputs].reports_dir` (override with `-o`).

---

## Roadmap snapshot (2025-10-30)

Refer to [ROADMAP.md](ROADMAP.md) for the full plan. Highlights for v1.0.0:

- Schema migrations and automated tests.
- Redaction system (manual + rule-based) with CLI and UI controls.
- Streamlit review app for prompt/action browsing and export.
- Markdown/CSV transparency reports filtered by repo, date, or session.
- Pipx-friendly packaging and documentation.

Beyond v1.0.0 we're targeting tagging, audit trails, API integrations, VS Code extensions, and compliance-ready exports.

---

## Operational assumptions

- **Architecture** - Components are wired manually; no dependency injection framework is in place yet. Larger deployments should plan for DI or service registries before extending the tool.
- **Session paths** - Ingest expects Codex logs under `~/.codex/sessions/<year>/<month>/<day>/file.jsonl` (or the Windows equivalent). Symlinks and junctions must preserve this structure and point to readable directories; atypical mount points are not traversed automatically.
- **Memory profile** - JSON payloads are read as-is with no max size enforcement. Very large sessions can exhaust memory; split oversized logs before ingesting or ingest them incrementally.
- **Concurrency** - SQLite writes run in a single process and rely on SQLite's default locking. Running multiple ingests against the same database concurrently is unsupported and may deadlock.
- **Encoding** - All file I/O assumes UTF-8. Convert logs encoded differently before processing.
- **Timestamps** - Session timestamps are stored verbatim. Downstream analytics should normalize timezones explicitly (e.g., convert to UTC) to avoid skew.

These constraints will be revisited as part of resilience and scaling work.

---

## Contributing & ethos

This is an "AI-assisted" project-experiments will happen-but the mandate is transparency:

- Every commit notes AI assistance.
- Raw logs remain user-owned; ingest only reads from configured paths.
- Redactions are first-class citizens with provenance.

Ideas, bug reports, and questions are welcome. Please review `AGENTS.md` for expectations before contributing.

---

## License

This project is licensed under the terms of the [MIT License](LICENSE).
