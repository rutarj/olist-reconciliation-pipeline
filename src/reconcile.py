"""Two-system reconciliation: what was sold (order_items) vs what was paid (order_payments).

The SQL does the work (sql/reconciliation/*.sql). This module runs it in order,
saves the evidence behind every bucket, builds the reconciliation exceptions and
returns summary numbers for metrics.json.
"""
from __future__ import annotations

import logging
from pathlib import Path
from string import Template

import duckdb
import pandas as pd

from .config import MATCH_TOLERANCE, SQL_DIR

log = logging.getLogger(__name__)

RECON_DIR = SQL_DIR / "reconciliation"

# Bucket definitions. Order matches the CASE in 02_categorize.sql.
# 'evidence' names the file in reports/evidence/ that justifies the rule.
CATEGORY_RULES = [
    {"category": "matched", "severity": "none",
     "rule": "|paid - sold| <= 0.01 BRL",
     "evidence": "tolerance set by the business requirement (1 cent)",
     "action": "none"},
    {"category": "rounding", "severity": "low",
     "rule": "2+ items and |gap| <= 0.01 x item count",
     "evidence": "rounding_by_item_count.csv: every gap between 0.02 and 0.10 is on a multi-item order and stays within 1 cent per item",
     "action": "none; raise tolerance to 1 cent per line if this noise matters"},
    {"category": "voucher_related", "severity": "medium",
     "rule": "a voucher is one of the payments and the totals differ",
     "evidence": "voucher_orders.csv: all are credit card + voucher splits where the combined value exceeds the order total",
     "action": "check voucher accounting: over-applied vouchers or card interest on the card part"},
    {"category": "installment_interest", "severity": "low",
     "rule": "paid > sold, credit card only, 2+ installments",
     "evidence": "interest_rate_card.csv and interest_by_installments.csv: paid/sold ratio sits on fixed multipliers that rise with installment count",
     "action": "book card interest as separate revenue so sold and paid tie out"},
    {"category": "untracked_discount", "severity": "medium",
     "rule": "paid < sold and the shortfall equals 5% or 10% of product price (+/- 0.02)",
     "evidence": "discount_share_of_price.csv: shortfalls land on exactly 5% or 10% of the price",
     "action": "record discounts in the order system, not only at payment"},
    {"category": "missing_items", "severity": "medium if canceled/unavailable, else high",
     "rule": "payment exists, no order items",
     "evidence": "missing_items_by_status.csv: nearly all are canceled or unavailable orders",
     "action": "confirm each payment was refunded; open orders need investigation"},
    {"category": "missing_payment", "severity": "high",
     "rule": "order items exist, no payment",
     "evidence": "direct: no payment row for the order_id",
     "action": "chase the payment record with the payment provider"},
    {"category": "orphan_no_order", "severity": "high",
     "rule": "items or payments reference an order_id that is not in orders",
     "evidence": "direct: order_id missing from orders",
     "action": "find the missing order header"},
    {"category": "empty_order", "severity": "high",
     "rule": "order exists with neither items nor payments",
     "evidence": "direct",
     "action": "check whether the order is a test or abandoned cart"},
    {"category": "unexplained", "severity": "high",
     "rule": "anything left",
     "evidence": "none: these are the ones a person has to look at",
     "action": "manual review, largest gaps first (reconciliation_ranked)"},
]


def _run_sql_file(con: duckdb.DuckDBPyConnection, path: Path, **params) -> None:
    con.execute(Template(path.read_text()).substitute(params))


def _evidence_queries() -> dict[str, str]:
    text = (RECON_DIR / "04_evidence.sql").read_text()
    out = {}
    for block in text.split("-- name: ")[1:]:
        name, _, sql = block.partition("\n")
        out[name.strip()] = sql.strip().rstrip(";")
    return out


def run_reconciliation(con: duckdb.DuckDBPyConnection, evidence_dir: Path | None = None) -> dict:
    _run_sql_file(con, RECON_DIR / "01_order_totals.sql")
    _run_sql_file(con, RECON_DIR / "02_categorize.sql", tolerance=MATCH_TOLERANCE)
    _run_sql_file(con, RECON_DIR / "03_gap_rankings.sql")

    con.register("category_rules_df", pd.DataFrame(CATEGORY_RULES))
    con.execute("create or replace table recon_category_rules as select * from category_rules_df")

    # Reconciliation exceptions: one per unmatched order, same shape as dq_exceptions.
    con.execute("""
        create or replace table recon_exceptions as
        select
            'reconciliation'              as table_name,
            o._row_id                     as record_id,
            r.order_id                    as record_key,
            'recon_' || r.gap_category    as check_name,
            'sold ' || coalesce(cast(r.expected_total as varchar), 'none') ||
            ' vs paid ' || coalesce(cast(r.paid_total as varchar), 'none') ||
            ' BRL, gap ' || cast(r.gap as varchar)  as reason,
            r.severity
        from reconciliation r
        left join (select order_id, min(_row_id) as _row_id from stg_orders group by 1) o using (order_id)
        where not r.is_matched
    """)

    # All exceptions in one place: data quality + reconciliation.
    con.execute("""
        create or replace table all_exceptions as
        select row_number() over (order by source, table_name, record_id, check_name) as exception_id, *
        from (
            select 'data_quality' as source, table_name, record_id, record_key, check_name, reason, severity
            from dq_exceptions
            union all
            select 'reconciliation', table_name, record_id, record_key, check_name, reason, severity
            from recon_exceptions
        )
    """)
    con.execute("""
        create or replace table exceptions_summary as
        select source, table_name, check_name, severity, count(*) as exceptions,
               count(distinct record_key) as distinct_records
        from all_exceptions
        group by source, table_name, check_name, severity
        order by case severity when 'high' then 1 when 'medium' then 2 else 3 end, exceptions desc
    """)
    con.execute("""
        create or replace table reconciliation_summary as
        select
            r.gap_category,
            any_value(k.severity)                          as severity,
            count(*)                                       as orders,
            round(100.0 * count(*) / sum(count(*)) over (), 4) as share_of_orders_pct,
            sum(r.expected_total)                          as sold_brl,
            sum(r.paid_total)                              as paid_brl,
            sum(r.gap)                                     as net_gap_brl,
            sum(r.abs_gap)                                 as abs_gap_brl,
            any_value(k.rule)                              as rule,
            any_value(k.evidence)                          as evidence,
            any_value(k.action)                            as action
        from reconciliation r
        left join recon_category_rules k on k.category = r.gap_category
        group by r.gap_category
        order by orders desc
    """)

    if evidence_dir is not None:
        evidence_dir.mkdir(parents=True, exist_ok=True)
        for name, sql in _evidence_queries().items():
            con.execute(sql).df().to_csv(evidence_dir / f"{name}.csv", index=False)
        reports_dir = evidence_dir.parent
        con.table("reconciliation_summary").df().to_csv(reports_dir / "reconciliation_summary.csv", index=False)
        con.table("exceptions_summary").df().to_csv(reports_dir / "exceptions_summary.csv", index=False)

    rows = con.execute("""
        select gap_category, count(*) as orders, sum(abs_gap) as abs_gap
        from reconciliation group by 1 order by orders desc
    """).fetchall()
    for cat, n, gap in rows:
        log.info("  %-22s %8s orders  %12s BRL", cat, f"{n:,}", f"{float(gap):,.2f}")
    return {"categories": {cat: n for cat, n, _ in rows}}
