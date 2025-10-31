# Codex Sessions Tool
<!-- markdownlint-disable MD042 -->
[![Status](https://img.shields.io/badge/status-experimental-blueviolet)](#)
[![Version](https://img.shields.io/badge/version-0.1.0--dev-orange)](#)
[![Python](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)](#)
<!-- markdownlint-enable MD042 -->
> **AI-assisted coding, radical transparency.**  
> This project is intentionally built in public with full disclosure of AI assistance. Every prompt, agent action, and generated artifact flows through the pipeline we’re building.

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
- 🛠️ **CLI utilities**
  - `python -m cli.group_session` groups events under each prompt for quick console or file review.
  - `python -m cli.ingest_session` ingests one or many sessions into SQLite with `--limit`, `--debug`, and `--verbose` modes.
- 🗺️ **Governance docs** – `AGENTS.md` sets behavioral guardrails; `ROADMAP.md` tracks milestones through v1.0.0 and beyond.
- 🧩 **Config scaffolding** – `user/config.example.toml` seeds per-user setup; actual secrets stay local via `.gitignore`.

---

## Getting started

> Requires Python 3.12+

1. **Clone & configure**

   ```bash
   git clone <repo-url>
   cd Codex-Sessions-Tool
   cp user/config.example.toml user/config.toml
   # edit user/config.toml to point at your Codex sessions directory
   ```

2. **Ingest a sample**

   ```bash
   python -m cli.ingest_session --debug -d reports/session_data.sqlite
   ```

   This ingests the first two sessions, logs verbose output, and writes to `reports/session_data.sqlite`.
3. **Explore prompts**

   ```bash
   python -m cli.group_session -o reports/first_session.txt
   ```

   Generates a grouped text report for the earliest session.

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
