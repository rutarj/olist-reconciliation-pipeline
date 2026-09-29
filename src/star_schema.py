"""Build the star schema (sql/star/star_schema.sql) and export it as CSV and Parquet."""
from __future__ import annotations

import logging
from pathlib import Path

import duckdb

from .config import SQL_DIR

log = logging.getLogger(__name__)

STAR_TABLES = ["fact_orders", "fact_reconciliation", "fact_exceptions",
               "dim_date", "dim_customer_state", "dim_payment_type", "dim_product_category"]


def build_star_schema(con: duckdb.DuckDBPyConnection, out_dir: Path | None = None) -> dict[str, int]:
    con.execute((SQL_DIR / "star" / "star_schema.sql").read_text())
    counts = {}
    for t in STAR_TABLES:
        counts[t] = con.execute(f"select count(*) from {t}").fetchone()[0]
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
            con.execute(f"copy {t} to '{(out_dir / f'{t}.parquet').as_posix()}' (format parquet, compression zstd)")
            con.execute(f"copy {t} to '{(out_dir / f'{t}.csv').as_posix()}' (header, delimiter ',')")
        log.info("  %-22s %9s rows", t, f"{counts[t]:,}")
    return counts
