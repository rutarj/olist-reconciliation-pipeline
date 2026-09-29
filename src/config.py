"""Paths and constants shared by every step. Change them here, nowhere else."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql"
CONTRACTS_FILE = ROOT / "config" / "contracts.yaml"

# logical table name -> raw file name
RAW_FILES = {
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}

# Reconciliation: gaps up to this many BRL count as a match.
MATCH_TOLERANCE = 0.01


@dataclass(frozen=True)
class Paths:
    raw: Path = ROOT / "data" / "raw"
    processed: Path = ROOT / "data" / "processed"
    reports: Path = ROOT / "reports"
    docs: Path = ROOT  # where rendered README.md / NOTES.md go
    db: str = ":memory:"
