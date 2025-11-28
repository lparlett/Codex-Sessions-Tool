"""Rule-based redaction loader and applier.

Purpose: Load YAML/JSON redaction rules and apply them with deterministic
precedence (AI-assisted by Codex GPT-5).
Author: Codex with Lauren Parlett
Date: 2025-11-27
Related tests: tests/test_redaction_rules.py
"""

from __future__ import annotations

import importlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence, TypedDict

DEFAULT_REPLACEMENT = "<REDACTED>"
DEFAULT_RULE_PATH = Path("user/redactions.yml")
ALLOWED_TYPES = ("regex", "marker", "literal")
ALLOWED_SCOPES = ("prompt", "field", "global")


class RuleSummary(TypedDict):
    """Structured summary for a single rule application."""

    count: int


@dataclass(frozen=True)
class RuleOptions:
    """Optional attributes for a rule."""

    scope: str = "prompt"
    replacement: str | None = None
    enabled: bool = True
    reason: str | None = None
    actor: str | None = None
    ignore_case: bool = True
    dotall: bool = False


@dataclass(frozen=True)
class RedactionRule:
    """Normalized redaction rule."""

    id: str
    type: str
    pattern: str
    options: RuleOptions = field(default_factory=RuleOptions)
    _compiled: re.Pattern[str] | None = field(
        default=None, init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        _validate_rule(self)
        flags = 0
        if self.ignore_case:
            flags |= re.IGNORECASE
        if self.dotall:
            flags |= re.DOTALL
        pattern_text = self.pattern
        if self.type == "literal":
            pattern_text = re.escape(self.pattern)
        compiled = re.compile(pattern_text, flags=flags)
        object.__setattr__(self, "_compiled", compiled)

    @property
    def compiled(self) -> re.Pattern[str]:
        """Return the compiled regex pattern."""

        if self._compiled is None:
            raise RuntimeError("Rule was not compiled.")
        return self._compiled

    @property
    def effective_replacement(self) -> str:
        """Replacement text or the global default."""

        return self.replacement or DEFAULT_REPLACEMENT

    @property
    def scope(self) -> str:
        return self.options.scope

    @property
    def replacement(self) -> str | None:
        return self.options.replacement

    @property
    def enabled(self) -> bool:
        return self.options.enabled

    @property
    def reason(self) -> str | None:
        return self.options.reason

    @property
    def actor(self) -> str | None:
        return self.options.actor

    @property
    def ignore_case(self) -> bool:
        return self.options.ignore_case

    @property
    def dotall(self) -> bool:
        return self.options.dotall


def load_rules(path: Path | str) -> list[RedactionRule]:
    """Load rules from a YAML or JSON file.

    Args:
        path: File path to a YAML or JSON rules document.

    Raises:
        ValueError: When the file is missing, malformed, or contains duplicates.
        SystemExit: When YAML is requested but PyYAML is not installed.
    """

    rules_path = Path(path)
    if not rules_path.exists():
        raise ValueError(f"Rules file not found: {rules_path}")

    raw_rules = _load_raw(rules_path)
    rules = [_parse_rule(entry, source=str(rules_path)) for entry in raw_rules]
    _enforce_unique_ids(rules, source=str(rules_path))
    return rules


def apply_rules(
    text: str, rules: Sequence[RedactionRule]
) -> tuple[str, dict[str, RuleSummary]]:
    """Apply rules in order and return the redacted text and per-rule counts.

    Manual database redactions should be applied *after* this function so they
    override file-based rules.
    """

    result = text
    summary: dict[str, RuleSummary] = {}

    for rule in rules:
        if not rule.enabled:
            continue

        if rule.type in {"regex", "literal"}:
            result, count = _apply_regex_rule(result, rule)
        else:
            result, count = _apply_marker_rule(result, rule)

        if count:
            summary[rule.id] = {"count": count}

    return result, summary


def _apply_regex_rule(text: str, rule: RedactionRule) -> tuple[str, int]:
    count = 0

    def _repl(_match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return rule.effective_replacement

    redacted = rule.compiled.sub(_repl, text)
    return redacted, count


def _apply_marker_rule(text: str, rule: RedactionRule) -> tuple[str, int]:
    count = 0

    def _repl(_match: re.Match[str]) -> str:
        nonlocal count
        count += 1
        return rule.effective_replacement

    redacted = rule.compiled.sub(_repl, text)
    return redacted, count


def _load_raw(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() in {".yml", ".yaml"}:
        try:
            yaml = importlib.import_module("yaml")
        except ModuleNotFoundError as exc:  # pragma: no cover - exercised in env
            raise SystemExit(
                "PyYAML is required to load YAML rule files. Install with "
                "'pip install pyyaml'."
            ) from exc
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
    else:
        parsed = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(parsed, list):
        raise ValueError(f"Rules file must contain a list, got {type(parsed)}")
    return [dict(item) for item in parsed]


def _parse_rule(entry: dict[str, Any], *, source: str) -> RedactionRule:
    required = ("id", "type", "pattern")
    for key in required:
        if key not in entry:
            raise ValueError(f"Missing required key '{key}' in {source}")

    options = RuleOptions(
        scope=str(entry.get("scope", "prompt")),
        replacement=entry.get("replacement"),
        enabled=bool(entry.get("enabled", True)),
        reason=_optional_str(entry.get("reason")),
        actor=_optional_str(entry.get("actor")),
        ignore_case=bool(entry.get("ignore_case", True)),
        dotall=bool(entry.get("dotall", False)),
    )
    return RedactionRule(
        id=str(entry["id"]),
        type=str(entry["type"]).lower(),
        pattern=str(entry["pattern"]),
        options=options,
    )


def _validate_rule(rule: RedactionRule) -> None:
    if rule.type not in ALLOWED_TYPES:
        raise ValueError(f"Invalid rule type '{rule.type}'. Allowed: {ALLOWED_TYPES}")
    if not rule.pattern.strip():
        raise ValueError("Rule pattern must be non-empty.")
    if rule.scope not in ALLOWED_SCOPES:
        raise ValueError(f"Invalid scope '{rule.scope}'. Allowed: {ALLOWED_SCOPES}")


def _enforce_unique_ids(rules: Iterable[RedactionRule], *, source: str) -> None:
    seen: set[str] = set()
    for rule in rules:
        if rule.id in seen:
            raise ValueError(f"Duplicate rule id '{rule.id}' in {source}")
        seen.add(rule.id)


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
