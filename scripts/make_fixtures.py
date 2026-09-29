"""Build tests/fixtures: a small, real slice of the Olist data for tests and CI.

Picks a fixed, seeded sample of orders so every reconciliation bucket and the main
data quality issues are represented, then keeps every related row (items, payments,
customers, products, sellers, reviews). Files keep the raw CSV names and columns, so
the pipeline runs on them unchanged.

Run after the full pipeline has downloaded data/raw:  python scripts/make_fixtures.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import RAW_FILES  # noqa: E402
from src.load import load_raw  # noqa: E402
from src.reconcile import run_reconciliation  # noqa: E402
from src.validate import run_validation  # noqa: E402

OUT = ROOT / "tests" / "fixtures"
PER_BUCKET = {"matched": 150, "missing_items": 8, "installment_interest": 8, "rounding": 4,
              "untracked_discount": 3, "voucher_related": 2, "unexplained": 2, "missing_payment": 1}
PER_DQ_CHECK = 3


def main() -> None:
    con = duckdb.connect()
    load_raw(con, ROOT / "data" / "raw")
    run_validation(con)
    run_reconciliation(con)
    con.execute("select setseed(0.42)")

    picks = []
    for cat, n in PER_BUCKET.items():
        picks += [r[0] for r in con.execute(
            "select order_id from reconciliation where gap_category = ? order by hash(order_id) limit ?",
            [cat, n]).fetchall()]
    picks += [r[0] for r in con.execute(f"""
        select record_key from (
            select record_key, row_number() over (partition by check_name order by hash(record_key)) as rn
            from dq_exceptions where table_name = 'orders')
        where rn <= {PER_DQ_CHECK}""").fetchall()]
    con.execute("create table pick as select distinct unnest(?) as order_id", [picks])

    OUT.mkdir(parents=True, exist_ok=True)
    queries = {
        "orders": "select * from raw_orders where order_id in (select order_id from pick)",
        "order_items": "select * from raw_order_items where order_id in (select order_id from pick)",
        "order_payments": "select * from raw_order_payments where order_id in (select order_id from pick)",
        "order_reviews": "select * from raw_order_reviews where order_id in (select order_id from pick)",
        "customers": "select * from raw_customers where customer_id in "
                     "(select customer_id from raw_orders where order_id in (select order_id from pick))",
        "products": "select * from raw_products where product_id in (select product_id from raw_order_items "
                    "where order_id in (select order_id from pick))",
        "sellers": "select * from raw_sellers where seller_id in (select seller_id from raw_order_items "
                   "where order_id in (select order_id from pick))",
        "category_translation": "select * from raw_category_translation",
    }
    for table, sql in queries.items():
        df = con.execute(f"select * exclude (_row_id) from ({sql}) order by _row_id").df()
        df.to_csv(OUT / RAW_FILES[table], index=False)
        print(f"{table:22s} {len(df):5d} rows")


if __name__ == "__main__":
    main()
