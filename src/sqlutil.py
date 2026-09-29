"""Small helpers for SQL files."""
from __future__ import annotations

import re
from pathlib import Path

_NAME = re.compile(r"^-- name: (\w+)\s*$", re.MULTILINE)


def named_queries(path: Path) -> dict[str, str]:
    """Split a .sql file into queries. Each query starts on a line of its own: '-- name: <name>'."""
    parts = _NAME.split(path.read_text())
    return {name: sql.strip().rstrip(";") for name, sql in zip(parts[1::2], parts[2::2])}
