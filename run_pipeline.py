"""Single entry point: python run_pipeline.py

Runs every step from raw CSVs to reports. Safe to re-run: every output is rebuilt from scratch.

  1. download + verify raw data (skipped with --no-download)
  2. load raw CSVs into DuckDB (as text)
  3. validate: schema contracts + business rules -> exceptions
  4. reconcile: sold (items) vs paid (payments) -> buckets
  5. star schema -> data/processed (CSV + Parquet)
  6. KPIs + forecast -> reports/metrics.json
  7. reports: summary.xlsx, dashboard.html
  8. docs: README.md, reports/FINDINGS_MEMO.md, NOTES.md, docs/DATA_DICTIONARY.md
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import duckdb

from src.config import Paths
from src.data_dictionary import build_data_dictionary
from src.download import ensure_raw_data
from src.forecast import forecast_table, run_forecast
from src.load import load_raw
from src.metrics import build_metrics, compute_kpis, write_metrics
from src.reconcile import run_reconciliation
from src.render_docs import render_all
from src.report_excel import build_excel
from src.report_html import build_dashboard
from src.star_schema import build_star_schema
from src.validate import run_validation

log = logging.getLogger("pipeline")


def run(paths: Paths, download: bool = True) -> dict:
    t0 = time.time()
    if download:
        log.info("step 1: download and verify raw data")
        ensure_raw_data(paths.raw)
    con = duckdb.connect(paths.db)

    log.info("step 2: load raw CSVs")
    raw_counts = load_raw(con, paths.raw)

    log.info("step 3: validate against schema contracts and business rules")
    dq = run_validation(con)

    log.info("step 4: reconcile sold (order_items) vs paid (order_payments)")
    recon = run_reconciliation(con, evidence_dir=paths.reports / "evidence")

    log.info("step 5: build star schema")
    star_counts = build_star_schema(con, paths.processed)

    log.info("step 6: KPIs and forecast")
    kpis = compute_kpis(con)
    forecast = run_forecast(con)
    forecast_table(forecast).to_csv(paths.processed / "forecast_monthly.csv", index=False)
    metrics = build_metrics(con, raw_counts=raw_counts, dq=dq, star_counts=star_counts, kpis=kpis, forecast=forecast)
    write_metrics(metrics, paths.reports / "metrics.json")

    log.info("step 7: reports")
    build_excel(con, metrics, kpis, paths.reports / "summary.xlsx")
    build_dashboard(con, metrics, paths.reports / "dashboard.html")

    log.info("step 8: docs (numbers read from metrics.json)")
    build_data_dictionary(con, paths.processed, paths.reports, paths.docs / "docs" / "DATA_DICTIONARY.md")
    for doc in render_all(paths.reports / "metrics.json", paths.docs, paths.reports):
        log.info("  rendered %s", doc)

    log.info("done in %.1fs", time.time() - t0)
    return {"metrics": metrics, "recon": recon, "con": con}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--raw-dir", type=Path, default=Paths.raw, help="folder with the raw CSVs")
    parser.add_argument("--out-dir", type=Path, default=None,
                        help="write data/processed and reports under this folder instead of the repo")
    parser.add_argument("--no-download", action="store_true", help="use the files already in --raw-dir")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%H:%M:%S")
    paths = Paths(raw=args.raw_dir)
    if args.out_dir:
        paths = Paths(raw=args.raw_dir, processed=args.out_dir / "processed", reports=args.out_dir / "reports",
                      docs=args.out_dir)
    run(paths, download=not args.no_download)


if __name__ == "__main__":
    main()
