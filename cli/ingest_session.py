# Purpose: command-line entry for ingesting Codex session logs into SQLite storage.
# Author: Codex with Lauren Parlett
# Date: 2025-10-30
# Related tests: TBD (planned)

"""CLI to ingest Codex session logs into SQLite."""

from __future__ import annotations

import argparse
import logging
from collections import Counter
from pathlib import Path

from src.parsers.session_parser import SessionDiscoveryError
from src.services.config import ConfigError, load_config
from src.services.ingest import ingest_session_file, ingest_sessions_in_directory


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest the earliest Codex session into an SQLite database.",
    )
    parser.add_argument(
        "--database",
        "-d",
        type=Path,
        default=Path("reports") / "session_data.sqlite",
        help="Path to the SQLite database (default: reports/session_data.sqlite).",
    )
    parser.add_argument(
        "--session",
        "-s",
        type=Path,
        help="Optional explicit session file to ingest instead of auto-discovery.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Optional cap on the number of session files to ingest (applies only when --session is not provided).",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging during ingest.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Debug mode: enable verbose logging and limit ingest to two files.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    verbose = args.verbose
    limit = args.limit

    if args.debug:
        verbose = True
        if limit is None or limit > 2:
            limit = 2

    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    try:
        config = load_config()
    except ConfigError as err:
        print(f"Configuration error: {err}")
        return

    if args.session:
        session_file = args.session
    else:
        try:
            summaries = list(
                ingest_sessions_in_directory(
                    config.sessions_root,
                    args.database,
                    limit=limit,
                    verbose=verbose,
                )
            )
        except SessionDiscoveryError as err:
            print(f"Session discovery error: {err}")
            return

        totals = Counter()
        for summary in summaries:
            print(f"Ingested: {summary['session_file']}")
            for key, value in summary.items():
                if key in {"file_id", "session_file"}:
                    continue
                if isinstance(value, int):
                    totals[key] += value
                print(f"  {key}: {value}")
            print()

        print(f"Database: {args.database}")
        print(f"Files processed: {len(summaries)}")
        print("Totals:")
        for key, value in totals.items():
            print(f"  {key}: {value}")
        return

    summary = ingest_session_file(session_file, args.database, verbose=verbose)

    print(f"Ingested session file: {session_file}")
    print(f"Database: {args.database}")
    print("Inserted rows:")
    for key, value in summary.items():
        if key in {"file_id", "session_file"}:
            continue
        print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
