"""Targeted tests for conftest module behavior (AI-assisted by Codex GPT-5)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any
from unittest import TestCase


TC = TestCase()


def test_conftest_sys_path_not_duplicated(monkeypatch: Any) -> None:
    """Re-importing conftest should not duplicate ROOT_DIR in sys.path."""

    root_dir = str(Path(__file__).parent.parent.resolve())
    path_list = list(sys.path)
    if root_dir not in path_list:
        path_list.append(root_dir)
    monkeypatch.setattr(sys, "path", path_list)
    count_before = path_list.count(root_dir)

    monkeypatch.delitem(sys.modules, "tests.conftest", raising=False)
    importlib.import_module("tests.conftest")
    count_after = sys.path.count(root_dir)

    TC.assertEqual(count_after, count_before)
