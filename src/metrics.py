"""Collect every number the reports and docs use into one dict -> reports/metrics.json.

Rule for this project: if a number appears in README.md, FINDINGS_MEMO.md or NOTES.md,
it comes from this file. Docs are rendered from templates that read metrics.json
(src/render_docs.py), so nobody types a number by hand.
"""
from __future__ import annotations

import datetime as dt
import decimal
import json
import math
from pathlib import Path

import duckdb
import pandas as pd

from .config import MATCH_TOLERANCE, SQL_DIR
from .sqlutil import named_queries

SINGLE_ROW = {"headline", "pareto", "delivery", "interest_rate_card_share", "missing_items", "sequence_gaps"}


def _clean(v):
    if isinstance(v, decimal.Decimal):
        return float(v)
    if isinstance(v, (pd.Timestamp, dt.date, dt.datetime)):
        return v.isoformat()
    if isinstance(v, float) and math.isnan(v):
        return None
    if hasattr(v, "item"):  # numpy scalar
        return _clean(v.item())
    if v is pd.NA or v is pd.NaT:
        return None
    return v


def _records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict(orient="records")]


def compute_kpis(con: duckdb.DuckDBPyConnection) -> dict[str, pd.DataFrame]:
    return {name: con.execute(sql).df() for name, sql in named_queries(SQL_DIR / "kpis.sql").items()}


def build_metrics(con, *, raw_counts: dict, dq: dict, star_counts: dict,
                  kpis: dict[str, pd.DataFrame], forecast: dict) -> dict:
    k = {name: (_records(df)[0] if name in SINGLE_ROW else _records(df)) for name, df in kpis.items()}
    h = k["headline"]

    dates = con.execute("""
        select min(order_purchase_timestamp)::date, max(order_purchase_timestamp)::date from stg_orders
    """).fetchone()
    dq_totals = con.execute("""
        select count(*),
               count(*) filter (where severity = 'high'),
               count(*) filter (where severity = 'medium'),
               count(*) filter (where severity = 'low'),
               count(distinct table_name || record_id)
        from dq_exceptions
    """).fetchone()
    rows_in = sum(raw_counts.values())
    quarantined = con.execute("select count(*) from dq_row_status where row_status = 'quarantined'").fetchone()[0]

    by_cat = {r["gap_category"]: r for r in k["gap_by_category"]}
    evidence = named_queries(SQL_DIR / "reconciliation" / "04_evidence.sql")
    interest_steps = {r["max_installments"]: r
                      for r in _records(con.execute(evidence["interest_by_installments"]).df())}

    series = {row["month"]: row["orders"] for row in forecast.get("series", [])}
    nov_uplift = None
    if series.get("2017-10") and series.get("2017-11"):
        nov_uplift = round(100.0 * (series["2017-11"] / series["2017-10"] - 1), 1)

    top_state = k["top_states"][0] if k["top_states"] else {}
    top_cat = k["top_categories"][0] if k["top_categories"] else {}

    value_mm = h["orders_value_mismatch"] or 0
    explained_mm = value_mm - (by_cat.get("unexplained", {}).get("orders", 0))
    check_counts: dict[str, int] = {}
    for r in k["exceptions_by_check"]:
        check_counts[r["check_name"]] = check_counts.get(r["check_name"], 0) + r["exceptions"]
    rv = {r["reconciliation_status"]: r for r in k["reviews_by_match"]}
    pareto = k["pareto"]

    return {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "currency": "BRL",
        "match_tolerance_brl": MATCH_TOLERANCE,
        "dataset": {
            "raw_rows": raw_counts,
            "raw_rows_total": rows_in,
            "tables_loaded": len(raw_counts),
            "first_purchase_date": dates[0].isoformat() if dates[0] else None,
            "last_purchase_date": dates[1].isoformat() if dates[1] else None,
        },
        "data_quality": {
            "checks_run": dq["checks_run"],
            "exceptions": dq_totals[0],
            "high": dq_totals[1],
            "medium": dq_totals[2],
            "low": dq_totals[3],
            "records_with_exceptions": dq_totals[4],
            "records_quarantined": quarantined,
            "pct_rows_clean": round(100.0 * (rows_in - dq_totals[4]) / rows_in, 2) if rows_in else None,
            "row_status": k["row_status"],
        },
        "reconciliation": {
            **h,
            "abs_gap_pct_of_paid": round(100.0 * h["abs_gap_brl"] / h["paid_brl"], 3) if h["paid_brl"] else None,
            "categories": k["gap_by_category"],
            "categories_used": len(k["gap_by_category"]),
            "value_mismatch_explained": explained_mm,
            "value_mismatch_explained_pct": round(100.0 * explained_mm / value_mm, 2) if value_mm else None,
            "interest_and_discount_pct_of_value_mismatch": round(
                100.0 * (by_cat.get("installment_interest", {}).get("orders", 0)
                         + by_cat.get("untracked_discount", {}).get("orders", 0)) / value_mm, 2) if value_mm else None,
            "unexplained_pct_of_orders": round(100.0 * h["orders_unexplained"] / h["orders_total"], 4)
            if h["orders_total"] else None,
            "by_category": by_cat,
            "pareto": {**pareto,
                       "pct_of_unmatched_orders": round(100.0 * pareto["orders_for_80pct_of_gap"]
                                                        / pareto["unmatched_orders"], 1)
                       if pareto["unmatched_orders"] else None},
            "interest": {**k["interest_rate_card_share"],
                         "median_gap_pct_2x": interest_steps.get(2, {}).get("median_gap_pct"),
                         "median_gap_pct_12x": interest_steps.get(12, {}).get("median_gap_pct"),
                         "by_installments": list(interest_steps.values())},
            "discount_split": k["discount_split"],
            "missing_items": k["missing_items"],
            "sequence_gaps": k["sequence_gaps"],
            "top_states": k["top_states"][:10],
            "top_state": top_state,
            "top_categories": k["top_categories"][:10],
            "top_category": top_cat,
            "payment_mix": k["payment_mix"],
        },
        "exceptions": {
            "total": int(sum(r["exceptions"] for r in k["exceptions_by_severity"])),
            "by_severity": k["exceptions_by_severity"],
            "by_severity_name": {r["severity"]: r["exceptions"] for r in k["exceptions_by_severity"]},
            "by_check_name": check_counts,
            "by_check": k["exceptions_by_check"],
        },
        "kpis": {
            "delivery": k["delivery"],
            "reviews_by_match": rv,
            "review_gap_matched_minus_unmatched": round(rv["matched"]["avg_review_score"]
                                                        - rv["unmatched"]["avg_review_score"], 2)
            if {"matched", "unmatched"} <= rv.keys() else None,
            "reviews_by_category": {r["gap_category"]: r for r in k["reviews_by_category"]},
            "monthly": k["monthly"],
        },
        "forecast": {**forecast, "nov_2017_uplift_vs_oct_pct": nov_uplift,
                     "horizon_months": len(forecast.get("forecast", [])),
                     "model_minus_baseline_mape_pp": round(forecast["best_model_mape_pct"]
                                                           - forecast["best_baseline_mape_pct"], 2)
                     if not forecast.get("skipped") else None},
        "star_schema_rows": star_counts,
    }


def write_metrics(metrics: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False, default=_clean) + "\n", encoding="utf-8")
