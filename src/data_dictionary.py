"""docs/DATA_DICTIONARY.md, generated from the real output tables.

Column names and types are read from DuckDB, descriptions come from DESCRIPTIONS below.
If a new column appears without a description the pipeline fails, so the dictionary
can never silently fall behind the data.
"""
from __future__ import annotations

from pathlib import Path

import duckdb

TABLES = {
    "fact_orders": ("One row per order in the orders table (first copy if an order_id is duplicated).", {
        "order_id": "Order id (32-char hash). Primary key.",
        "customer_id": "Customer id for this order. Olist issues one customer_id per order.",
        "state_code": "Customer state, 2 letters. FK to dim_customer_state. UNKNOWN if the customer is missing.",
        "purchase_date_key": "Purchase date as yyyymmdd. FK to dim_date (active relationship).",
        "delivered_date_key": "Delivery-to-customer date as yyyymmdd. FK to dim_date (inactive relationship). Blank if not delivered.",
        "estimated_date_key": "Estimated delivery date as yyyymmdd.",
        "order_status": "Order status from the source: created, approved, invoiced, processing, shipped, delivered, canceled, unavailable.",
        "payment_type": "Payment type carrying the largest share of the order value. FK to dim_payment_type. 'none' if no payment.",
        "category_key": "Portuguese category of the most expensive item. FK to dim_product_category. 'unknown' if none.",
        "order_purchase_timestamp": "When the customer placed the order.",
        "order_approved_at": "When the payment was approved.",
        "order_delivered_carrier_date": "When the order was handed to the carrier.",
        "order_delivered_customer_date": "When the customer received the order.",
        "order_estimated_delivery_date": "Delivery date promised to the customer.",
        "item_count": "Number of item rows for the order (0 if none).",
        "product_value": "Sum of item prices, BRL.",
        "freight_value": "Sum of item freight charges, BRL.",
        "sold_value": "System A total: product_value + freight_value, BRL.",
        "paid_value": "System B total: sum of payment values, BRL.",
        "is_delivered": "True if a customer delivery date exists.",
        "is_on_time": "True if delivered on or before the estimated date (date level). Blank if not delivered.",
        "delivery_days": "Days from purchase to customer delivery.",
        "review_score": "Average review score (1 to 5) for the order. Blank if no review.",
        "review_count": "Number of reviews for the order.",
        "is_matched": "True if paid and sold agree within the tolerance (R$ 0.01).",
        "gap_category": "Reconciliation bucket (see fact_reconciliation).",
        "has_dq_exception": "True if the order, its items or payments have a high or medium data quality exception.",
    }),
    "fact_reconciliation": ("One row per order_id found in ANY of orders, order_items or order_payments.", {
        "order_id": "Order id. Primary key.",
        "state_code": "Customer state. FK to dim_customer_state.",
        "purchase_date_key": "Purchase date as yyyymmdd. FK to dim_date.",
        "payment_type": "Main payment type. FK to dim_payment_type.",
        "category_key": "Category of the most expensive item. FK to dim_product_category.",
        "in_orders": "True if the order_id exists in the orders table (False = orphan items/payments).",
        "order_status": "Order status.",
        "item_count": "Item rows in System A. Blank if none.",
        "payment_count": "Payment rows in System B. Blank if none.",
        "payment_types": "All payment types used, joined with '+', e.g. credit_card+voucher.",
        "max_installments": "Highest installment count across the order's payments.",
        "has_voucher": "True if any payment is a voucher.",
        "product_value": "Sum of item prices, BRL.",
        "freight_value": "Sum of freight, BRL.",
        "expected_total": "System A: product_value + freight_value, BRL. Blank if no items.",
        "paid_total": "System B: sum of payment_value, BRL. Blank if no payments.",
        "gap": "paid_total - expected_total (missing side counts as 0), BRL. Positive = customer paid more.",
        "abs_gap": "Absolute value of gap, BRL.",
        "gap_pct": "gap / expected_total x 100. Blank if a side is missing.",
        "paid_to_sold_ratio": "paid_total / expected_total, 4 decimals. Used to find the card interest rate table.",
        "is_matched": "True if abs_gap <= R$ 0.01 and both sides exist.",
        "gap_category": "Bucket: matched, rounding, voucher_related, installment_interest, untracked_discount, missing_items, missing_payment, orphan_no_order, empty_order, unexplained.",
        "severity": "high / medium / low for unmatched orders; blank if matched.",
        "has_dq_exception": "True if a high/medium data quality exception touches this order.",
        "gap_rank_in_month": "DENSE_RANK of abs_gap within the purchase month (1 = largest). Unmatched only.",
        "gap_rank_in_state": "DENSE_RANK of abs_gap within the customer state (1 = largest). Unmatched only.",
        "cumulative_gap_share": "Running share (0 to 1) of all unmatched money, largest gaps first. Pareto analysis.",
    }),
    "fact_exceptions": ("One row per exception from data quality checks or reconciliation. Bad rows are listed here, never deleted.", {
        "exception_id": "Exception id. Primary key.",
        "source": "data_quality or reconciliation.",
        "table_name": "Table the record came from (orders, order_items, ..., or reconciliation).",
        "record_id": "Row number of the record in its raw file (1 = first data row). Stable id even when keys are duplicated.",
        "record_key": "Natural key of the record, e.g. order_id|order_item_id.",
        "order_id": "Order id when the record belongs to an order, else blank.",
        "check_name": "Check that failed, e.g. duplicate_key, carrier_before_purchase, recon_missing_items.",
        "reason": "Plain-language reason with the offending values.",
        "severity": "high = money or counts wrong if trusted; medium = suspicious; low = informational.",
        "purchase_date_key": "Purchase date of the related order. FK to dim_date.",
        "state_code": "Customer state of the related order. FK to dim_customer_state.",
    }),
    "dim_date": ("One row per calendar day from the first purchase to the last delivery or estimate.", {
        "date_key": "yyyymmdd integer. Primary key.",
        "date": "Calendar date. Mark as date table in Power BI.",
        "year": "Year.", "quarter": "Quarter 1 to 4.", "month": "Month 1 to 12.", "month_name": "Month name.",
        "year_month": "yyyy-mm text, for slicers.", "month_start": "First day of the month.",
        "iso_week": "ISO week number.", "day_of_week": "ISO day of week, 1 = Monday.", "day_name": "Day name.",
        "is_weekend": "True on Saturday and Sunday.",
    }),
    "dim_customer_state": ("The 27 Brazilian federative units plus UNKNOWN.", {
        "state_code": "2-letter code. Primary key.", "state_name": "State name.",
        "region": "IBGE macro-region: North, Northeast, Center-West, Southeast, South.",
    }),
    "dim_payment_type": ("Every payment type seen in the data plus 'none'.", {
        "payment_type": "Payment type. Primary key.", "description": "Plain-language description.",
        "is_card": "True for credit and debit card.",
    }),
    "dim_product_category": ("Product categories with English names from the translation file.", {
        "category_key": "Portuguese category name as in the source, or 'unknown'. Primary key.",
        "category_name_pt": "Portuguese name (blank for unknown).",
        "category_name_en": "English name; falls back to the Portuguese name when no translation exists.",
        "has_translation": "False for categories missing from the translation file.",
    }),
}

FILES = {
    "data/processed/forecast_monthly.csv": ("Monthly orders: actuals, holdout predictions per model, and the forecast.", {
        "month": "yyyy-mm.", "series": "'actual' or the model name.",
        "row_type": "actual, holdout (prediction for a known month) or forecast (future month).",
        "orders": "Order count (actual or predicted).",
        "used_in_model": "True if the month is inside the complete-month window used for training/holdout.",
        "month_start": "First day of the month (date).",
    }),
    "reports/reconciliation_summary.csv": ("One row per reconciliation bucket.", {
        "gap_category": "Bucket.", "severity": "Severity rule for the bucket.", "orders": "Orders in the bucket.",
        "share_of_orders_pct": "Orders in bucket / all orders x 100.", "sold_brl": "Sum of expected_total, BRL.",
        "paid_brl": "Sum of paid_total, BRL.", "net_gap_brl": "Sum of gap, BRL.", "abs_gap_brl": "Sum of abs_gap, BRL.",
        "rule": "The rule that puts an order in this bucket.", "evidence": "Where the rule comes from.",
        "action": "What the business should do.",
    }),
    "reports/exceptions_summary.csv": ("Exceptions grouped by source, table, check and severity.", {
        "source": "data_quality or reconciliation.", "table_name": "Table.", "check_name": "Check.",
        "severity": "Severity.", "exceptions": "Exception rows.", "distinct_records": "Distinct record keys.",
    }),
}


def _table_md(title: str, desc: str, cols: list[tuple[str, str]], docs: dict[str, str]) -> str:
    missing = [c for c, _ in cols if c not in docs]
    if missing:
        raise KeyError(f"{title}: no description for {missing}. Add them to src/data_dictionary.py")
    lines = [f"## `{title}`", "", desc, "", "| Column | Type | Description |", "|---|---|---|"]
    lines += [f"| `{c}` | {t} | {docs[c]} |" for c, t in cols]
    return "\n".join(lines) + "\n"


def build_data_dictionary(con: duckdb.DuckDBPyConnection, processed: Path, reports: Path, out: Path) -> None:
    parts = ["<!-- GENERATED FILE by src/data_dictionary.py. Edit the descriptions there. -->",
             "# Data dictionary", "",
             "Every output table and column. Money is in Brazilian real (BRL). Star schema files are in "
             "`data/processed/` as both CSV and Parquet. Relationships: see `dashboard/POWERBI_SPEC.md`.", ""]
    for t, (desc, docs) in TABLES.items():
        cols = [(r[0], r[1]) for r in con.execute(f"describe {t}").fetchall()]
        parts.append(_table_md(t, desc, cols, docs))
    for rel, (desc, docs) in FILES.items():
        path = (processed if rel.startswith("data/") else reports) / Path(rel).name
        cols = [(r[0], r[1]) for r in con.execute(f"describe select * from read_csv_auto('{path.as_posix()}')").fetchall()]
        parts.append(_table_md(rel, desc, cols, docs))
    parts += ["## `reports/evidence/*.csv`", "",
              "One file per evidence query in `sql/reconciliation/04_evidence.sql`. Each file is the data behind a "
              "reconciliation bucket rule: `rounding_by_item_count`, `interest_rate_card`, `interest_by_installments`, "
              "`discount_share_of_price`, `missing_items_by_status`, `sequence_gap_orders_reconcile`, `voucher_orders`.", "",
              "## `reports/metrics.json`", "",
              "Every number used in README.md, reports/FINDINGS_MEMO.md and NOTES.md. Top-level sections: `dataset`, "
              "`data_quality`, `reconciliation`, `exceptions`, `kpis`, `forecast`, `star_schema_rows`. Percentages are "
              "0 to 100, money is BRL.", ""]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(parts), encoding="utf-8")
