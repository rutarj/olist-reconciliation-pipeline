"""Render README.md, reports/FINDINGS_MEMO.md and NOTES.md from templates + metrics.json.

Why: every number in the docs must come from the pipeline. Templates in docs/templates/
hold the words; numbers are placeholders that read reports/metrics.json.

Placeholder syntax
  {{ reconciliation.match_rate_pct | pct }}      value at a dotted path, then a format
  {{ reconciliation.categories.0.orders | int }} list items by index
  {{ exceptions.by_check_name.duplicate_key? | int }}  trailing ? = 0 if the path is missing
  {{ table: forecast.scores | model:Model, holdout_mape_pct:Holdout MAPE:pct }}
                                                 a markdown table from a list of dicts:
                                                 key:Header[:format] per column

Formats: int (99,441), num1/num2/num3 (fixed decimals), pct (98.91%), pct1, pct3,
brl (R$ 166,004.63), brl0 (R$ 166,005), stars (4.11), text (default: as is), code (`x`).
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from .config import ROOT

log = logging.getLogger(__name__)

TEMPLATES = ROOT / "docs" / "templates"
PLACEHOLDER = re.compile(r"\{\{\s*(.+?)\s*\}\}")


class MissingMetric(KeyError):
    pass


def _get(metrics: dict, path: str):
    default_zero = path.endswith("?")
    node = metrics
    for part in path.rstrip("?").split("."):
        try:
            node = node[int(part)] if isinstance(node, list) else node[part]
        except (KeyError, IndexError, ValueError, TypeError):
            if default_zero:
                return 0
            raise MissingMetric(path) from None
    return node


def fmt(value, style: str = "text") -> str:
    if value is None:
        return "n/a"
    s = style.strip()
    if s == "int":
        return f"{int(round(value)):,}"
    if s in {"num1", "num2", "num3"}:
        return f"{value:,.{s[-1]}f}"
    if s in {"pct", "pct1", "pct3"}:
        digits = {"pct": 2, "pct1": 1, "pct3": 3}[s]
        return f"{value:.{digits}f}%"
    if s == "brl":
        return f"R$ {value:,.2f}"
    if s == "brl0":
        return f"R$ {value:,.0f}"
    if s == "stars":
        return f"{value:.2f}"
    if s == "code":
        return f"`{value}`"
    if s == "text":
        return str(value)
    raise ValueError(f"unknown format {style!r}")


def _table(metrics: dict, spec: str, strict: bool) -> str:
    path, _, cols = spec.partition("|")
    rows = _get(metrics, path.strip())
    columns = []
    for col in cols.split(","):
        key, header, *style = [p.strip() for p in col.split(":")]
        columns.append((key, header, style[0] if style else "text"))
    lines = ["| " + " | ".join(h for _, h, _ in columns) + " |",
             "|" + "|".join("---:" if st not in {"text", "code"} else "---" for _, _, st in columns) + "|"]
    for r in rows:
        lines.append("| " + " | ".join(fmt(r.get(k), st) for k, _, st in columns) + " |")
    return "\n".join(lines)


def render(template: str, metrics: dict, strict: bool = True) -> str:
    def replace(m: re.Match) -> str:
        expr = m.group(1)
        try:
            if expr.startswith("table:"):
                return _table(metrics, expr[len("table:"):], strict)
            path, _, style = expr.partition("|")
            return fmt(_get(metrics, path.strip()), style or "text")
        except MissingMetric as exc:
            if strict:
                raise
            log.warning("metric %s missing, rendered as n/a", exc)
            return "n/a"

    out = PLACEHOLDER.sub(replace, template)
    if "{{" in out:
        raise ValueError("unrendered placeholder left in output")
    return out


# template file -> output path relative to the docs root / reports dir
OUTPUTS = {
    "README.md.tmpl": ("docs", "README.md"),
    "NOTES.md.tmpl": ("docs", "NOTES.md"),
    "FINDINGS_MEMO.md.tmpl": ("reports", "FINDINGS_MEMO.md"),
}


def render_all(metrics_path: Path, docs_root: Path, reports_dir: Path, strict: bool = False) -> list[Path]:
    metrics = json.loads(metrics_path.read_text(encoding="utf-8"))
    written = []
    for tmpl, (where, name) in OUTPUTS.items():
        src = TEMPLATES / tmpl
        if not src.exists():
            continue
        out = (docs_root if where == "docs" else reports_dir) / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(render(src.read_text(encoding="utf-8"), metrics, strict=strict), encoding="utf-8")
        written.append(out)
    return written
