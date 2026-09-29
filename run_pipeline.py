"""Single entry point: python run_pipeline.py

Runs every step from raw CSVs to reports. Safe to re-run: outputs are rebuilt from scratch.
"""
from __future__ import annotations

import argparse
import logging
import time
from pathlib import Path

import duckdb

from src.config import Paths
from src.download import ensure_raw_data
from src.load import load_raw
from src.validate import run_validation
from src.reconcile import run_reconciliation

log = logging.getLogger("pipeline")


def run(paths: Paths, download: bool = True) -> dict:
    t0 = time.time()
    if download:
        ensure_raw_data(paths.raw)
    con = duckdb.connect(paths.db)

    log.info("step 1: load raw CSVs")
    raw_counts = load_raw(con, paths.raw)

    log.info("step 2: validate against schema contracts and business rules")
    dq = run_validation(con)

    log.info("step 3: reconcile sold (order_items) vs paid (order_payments)")
    recon = run_reconciliation(con, evidence_dir=paths.reports / "evidence")

    log.info("done in %.1fs", time.time() - t0)
    return {"raw_counts": raw_counts, "dq": dq, "recon": recon, "con": con}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=Paths.raw)
    parser.add_argument("--no-download", action="store_true", help="use files already in --raw-dir")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S")
    run(Paths(raw=args.raw_dir), download=not args.no_download)


if __name__ == "__main__":
    main()
