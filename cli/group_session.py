# Purpose: provide human-readable grouping of Codex session logs for quick review.
# Author: Codex with Lauren Parlett
# Date: 2025-10-30
# Related tests: TBD (planned)

"""Simple CLI to group Codex session events by user prompts."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from textwrap import indent

from src.parsers.session_parser import (
    SessionDiscoveryError,
    find_first_session_file,
    group_by_user_messages,
    load_session_events,
)
from src.services.config import ConfigError, load_config


def shorten(text: str, limit: int = 120) -> str:
    """Return text truncated to ``limit`` characters with ellipsis."""

    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def describe_event(event: dict) -> str:
    """Build a concise description for an event."""

    event_type = event.get("type", "<unknown>")
    timestamp = event.get("timestamp", "?")
    payload = event.get("payload", {})
    payload_type = payload.get("type") if isinstance(payload, dict) else None

    summary_lines: list[str] = []

    summary = f"{event_type}"
    if payload_type:
        summary += f" ({payload_type})"
    summary += f" @ {timestamp}"
    summary_lines.append(summary)

    if not isinstance(payload, dict):
        return "\n".join(summary_lines)

    if event_type == "event_msg" and payload_type == "agent_reasoning":
        text = payload.get("text")
        if isinstance(text, str) and text.strip():
            summary_lines.append(indent("reasoning: " + shorten(text, 500), "    "))
    elif event_type == "event_msg" and payload_type == "token_count":
        rate_limits = payload.get("rate_limits", {})
        if isinstance(rate_limits, dict):
            for label in ("primary", "secondary"):
                data = rate_limits.get(label)
                if isinstance(data, dict):
                    used_percent = data.get("used_percent")
                    window_minutes = data.get("window_minutes")
                    resets = data.get("resets_at") or data.get("resets_in_seconds")
                    detail = f"{label}: {used_percent}% used of {window_minutes} min window"
                    if resets is not None:
                        detail += f", resets {resets}"
                    summary_lines.append(indent(detail, "    "))
    elif event_type == "event_msg" and payload_type == "agent_message":
        message = payload.get("message")
        if isinstance(message, str) and message.strip():
            summary_lines.append(indent(shorten(message, 500), "    message: "))
    elif event_type == "response_item":
        subtype = payload_type
        if subtype == "reasoning":
            summary_texts = payload.get("summary")
            if isinstance(summary_texts, list) and summary_texts:
                text_entry = summary_texts[0]
                text = text_entry.get("text") if isinstance(text_entry, dict) else None
                if isinstance(text, str):
                    summary_lines.append(indent("summary: " + shorten(text, 500), "    "))
        if subtype == "message":
            content = payload.get("content")
            if isinstance(content, list):
                texts = [
                    item.get("text")
                    for item in content
                    if isinstance(item, dict) and isinstance(item.get("text"), str)
                ]
                if texts:
                    summary_lines.append(indent(shorten(" ".join(texts), 500), "    message: "))
        if subtype == "function_call":
            name = payload.get("name")
            arguments = payload.get("arguments")
            if name:
                summary_lines.append(indent(f"function: {name}", "    "))
            if isinstance(arguments, str) and arguments.strip():
                summary_lines.append(indent("args: " + shorten(arguments, 500), "    "))
        if subtype == "function_call_output":
            output = payload.get("output")
            if isinstance(output, str):
                summary_lines.append(indent("output: " + shorten(output, 500), "    "))
    elif payload_type == "turn_context":
        cwd = payload.get("cwd")
        if isinstance(cwd, str):
            summary_lines.append(indent(f"cwd: {cwd}", "    "))
    elif event_type == "event_msg" and payload_type == "turn_aborted":
        reason = payload.get("reason")
        if isinstance(reason, str):
            summary_lines.append(indent(f"reason: {reason}", "    "))
    elif event_type == "turn_context":
        cwd = payload.get("cwd")
        if isinstance(cwd, str):
            summary_lines.append(indent(f"cwd: {cwd}", "    "))

    return "\n".join(summary_lines)


def build_parser() -> argparse.ArgumentParser:
    """Build argument parser for the CLI."""

    parser = argparse.ArgumentParser(
        description="Group Codex session events by user prompts.",
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        help="Write grouped output to the given text file (in addition to console).",
    )
    return parser


def write_report(output_path: Path, lines: list[str]) -> None:
    """Write grouped output to file with parent directory creation."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"\nReport written to {output_path}")


def main() -> None:
    """Entry point for the grouping CLI."""

    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except ValueError:
            # Some streams (like redirected output) may not support reconfigure.
            pass

    parser = build_parser()
    args = parser.parse_args()
    captured_output: list[str] = []

    try:
        config = load_config()
    except ConfigError as err:
        message = f"Configuration error: {err}"
        print(message)
        captured_output.append(message)
        return

    try:
        session_file = find_first_session_file(config.sessions_root)
    except SessionDiscoveryError as err:
        message = f"Session discovery error: {err}"
        print(message)
        captured_output.append(message)
        return

    events = load_session_events(session_file)
    prelude, groups = group_by_user_messages(events)

    header = f"Session file: {session_file}"
    print(header)
    captured_output.append(header)

    if prelude:
        captured_output.append("")
        captured_output.append("-- Session Prelude --")
        print("\n-- Session Prelude --")
        for event in prelude:
            description = indent(describe_event(event), "  ")
            print(description)
            captured_output.append(description)

    if not groups:
        message = "\nNo user messages found in session."
        print(message)
        captured_output.append(message)
        if args.output:
            write_report(args.output, captured_output)
        return

    for index, group in enumerate(groups, start=1):
        user_event = group["user"]
        user_payload = user_event.get("payload", {})
        prompt = user_payload.get("message", "").strip() if isinstance(user_payload, dict) else ""

        title = f"\n== Prompt {index} @ {user_event.get('timestamp', '?')} =="
        prompt_text = indent(shorten(prompt, limit=500) or "<empty prompt>", "  ")
        print(title)
        print(prompt_text)
        captured_output.append(title)
        captured_output.append(prompt_text)

        if not group["events"]:
            print("  (No subsequent events recorded.)")
            captured_output.append("  (No subsequent events recorded.)")
            continue

        print("  -- Following events --")
        captured_output.append("  -- Following events --")
        for event in group["events"]:
            description = indent(describe_event(event), "    ")
            print(description)
            captured_output.append(description)

    if args.output:
        write_report(args.output, captured_output)


if __name__ == "__main__":
    main()
