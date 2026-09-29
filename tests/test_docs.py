"""Docs never drift from the numbers: README, memo and notes are exactly what the templates render from metrics.json."""
from __future__ import annotations

import json

import pytest

from src.config import ROOT
from src.render_docs import OUTPUTS, TEMPLATES, MissingMetric, fmt, render

METRICS = ROOT / "reports" / "metrics.json"


@pytest.mark.skipif(not METRICS.exists(), reason="run python run_pipeline.py first")
@pytest.mark.parametrize("template", list(OUTPUTS))
def test_committed_docs_match_metrics(template):
    where, name = OUTPUTS[template]
    committed = (ROOT / name) if where == "docs" else (ROOT / "reports" / name)
    if not (TEMPLATES / template).exists():
        pytest.skip(f"{template} not written yet")
    expected = render((TEMPLATES / template).read_text(encoding="utf-8"),
                      json.loads(METRICS.read_text(encoding="utf-8")), strict=True)
    assert committed.read_text(encoding="utf-8") == expected, \
        f"{name} is out of date or was edited by hand. Edit docs/templates/{template} and re-run the pipeline."


def test_render_formats():
    assert fmt(99441, "int") == "99,441"
    assert fmt(98.9149, "pct") == "98.91%"
    assert fmt(166004.63, "brl") == "R$ 166,004.63"
    assert render("{{ a.b | int }} / {{ missing? | int }}", {"a": {"b": 3}}) == "3 / 0"


def test_missing_metric_fails_loudly():
    with pytest.raises(MissingMetric):
        render("{{ not.there }}", {}, strict=True)
