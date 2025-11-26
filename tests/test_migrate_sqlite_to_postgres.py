"""Additional tests for migrate_sqlite_to_postgres (AI-assisted by Codex GPT-5)."""

# pylint: disable=import-error,protected-access,too-few-public-methods

from __future__ import annotations

import sqlite3
import unittest
from pathlib import Path
from typing import Any

import pytest

from cli import migrate_sqlite_to_postgres as migrate_cli

TC = unittest.TestCase()


class _DummyConn:
    """Simple connection stub tracking close() calls."""

    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _DummyPgConn:
    """Postgres connection stub supporting context manager usage."""

    def __init__(self) -> None:
        self.closed = False
        self.executed: list[Any] = []

    def __enter__(self: "_DummyPgConn") -> "_DummyPgConn":
        return self

    def __exit__(
        self,
        exc_type: BaseException | None,
        exc: BaseException | None,
        tb: object,
    ) -> None:
        return None

    def cursor(self) -> "_DummyPgConn":
        return self

    def execute(
        self, statement: Any, _params: Any | None = None
    ) -> None:  # pylint: disable=unused-argument
        self.executed.append(statement)

    def fetchone(self) -> tuple[int]:
        return (1,)

    def commit(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def test_open_sqlite_missing_path_exits(tmp_path: Path) -> None:
    """_open_sqlite should exit when the database file is missing."""

    missing = tmp_path / "missing.sqlite"
    with pytest.raises(SystemExit):
        migrate_cli._open_sqlite(missing)  # pylint: disable=protected-access


def test_table_counts_validates_allowlist(tmp_path: Path) -> None:
    """_table_counts should reject unexpected table names."""

    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE files (id INTEGER)")
    conn.commit()

    with pytest.raises(SystemExit):
        migrate_cli._table_counts(
            conn, ["not_allowed"]
        )  # pylint: disable=protected-access
    conn.close()


def test_run_dry_run_closes_connections(monkeypatch: pytest.MonkeyPatch) -> None:
    """run_dry_run should close both connections and return counts."""

    dummy_sqlite = _DummyConn()
    dummy_pg = _DummyPgConn()
    monkeypatch.setattr(migrate_cli, "_open_sqlite", lambda path: dummy_sqlite)
    monkeypatch.setattr(migrate_cli, "_open_postgres", lambda dsn: dummy_pg)
    monkeypatch.setattr(
        migrate_cli,
        "_table_counts",
        lambda conn, tables: {"files": 1, "sessions": 2},
    )
    monkeypatch.setattr(
        migrate_cli,
        "_table_counts_postgres",
        lambda conn, tables: {"files": 0, "sessions": 0},
    )

    summary = migrate_cli.run_dry_run(Path("src.sqlite"), "postgres://dsn")
    TC.assertEqual(summary["source_counts"]["files"], 1)
    TC.assertEqual(summary["target_counts"]["sessions"], 0)
    TC.assertTrue(dummy_sqlite.closed)
    TC.assertTrue(dummy_pg.closed)


def test_migrate_calls_copy_pipeline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """migrate should build schema then call ensure_empty and copy helpers."""

    dummy_sqlite = _DummyConn()
    dummy_pg = _DummyPgConn()
    called = {"ensure": 0, "copy": 0}

    monkeypatch.setattr(migrate_cli, "_open_sqlite", lambda path: dummy_sqlite)
    monkeypatch.setattr(migrate_cli, "_open_postgres", lambda dsn: dummy_pg)
    monkeypatch.setattr(
        migrate_cli,
        "_ensure_target_empty",
        lambda conn, tables: called.__setitem__("ensure", called["ensure"] + 1),
    )
    monkeypatch.setattr(
        migrate_cli,
        "_copy_all_tables",
        lambda sqlite_conn, pg_conn, tables, batch_size: called.__setitem__(
            "copy", called["copy"] + 1
        ),
    )

    migrate_cli.migrate(tmp_path / "source.sqlite", "postgres://dsn", batch_size=10)

    TC.assertEqual(called["ensure"], 1)
    TC.assertEqual(called["copy"], 1)
    TC.assertTrue(dummy_sqlite.closed)
    TC.assertTrue(dummy_pg.closed)


def test_ensure_target_empty_raises_on_nonempty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """_ensure_target_empty should abort when target tables contain rows."""

    monkeypatch.setattr(
        migrate_cli,
        "_table_counts_postgres",
        lambda conn, tables: {"files": 1, "sessions": 0},
    )

    with pytest.raises(SystemExit):
        migrate_cli._ensure_target_empty(
            _DummyPgConn(), ("files", "sessions")
        )  # pylint: disable=protected-access
