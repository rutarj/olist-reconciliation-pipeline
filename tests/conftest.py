"""Shared test helpers.

Every test works on a fresh copy of tests/fixtures (a small real slice of Olist),
injects bad rows into the copy, runs the pipeline steps and checks what came out.
The fixture files themselves are never modified.
"""
from __future__ import annotations

import csv
import shutil
import sys
from pathlib import Path

import duckdb
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import RAW_FILES  # noqa: E402
from src.load import load_raw  # noqa: E402
from src.reconcile import run_reconciliation  # noqa: E402
from src.validate import run_validation  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"


class RawCopy:
    """A throwaway copy of the fixture CSVs that tests can corrupt on purpose."""

    def __init__(self, path: Path):
        self.path = path

    def file(self, table: str) -> Path:
        return self.path / RAW_FILES[table]

    def read(self, table: str) -> list[dict]:
        with open(self.file(table), newline="", encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def write(self, table: str, rows: list[dict]) -> None:
        with open(self.file(table), newline="", encoding="utf-8-sig") as f:
            header = next(csv.reader(f))
        with open(self.file(table), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=header)
            w.writeheader()
            w.writerows(rows)

    def append(self, table: str, *rows: dict) -> None:
        self.write(table, self.read(table) + list(rows))

    def update(self, table: str, match: dict, **changes) -> dict:
        """Change the first row matching `match`. Returns the updated row."""
        rows = self.read(table)
        for r in rows:
            if all(r[k] == v for k, v in match.items()):
                r.update({k: str(v) for k, v in changes.items()})
                self.write(table, rows)
                return r
        raise KeyError(f"no {table} row matches {match}")

    def run(self) -> duckdb.DuckDBPyConnection:
        con = duckdb.connect()
        load_raw(con, self.path)
        run_validation(con)
        run_reconciliation(con)
        return con


@pytest.fixture
def raw(tmp_path) -> RawCopy:
    dst = tmp_path / "raw"
    shutil.copytree(FIXTURES, dst)
    return RawCopy(dst)


@pytest.fixture(scope="session")
def clean_run() -> duckdb.DuckDBPyConnection:
    """Pipeline on the untouched fixtures (shared, read only)."""
    con = duckdb.connect()
    load_raw(con, FIXTURES)
    run_validation(con)
    run_reconciliation(con)
    return con


def exceptions(con, table: str | None = None, check: str | None = None) -> list[tuple]:
    sql = "select table_name, record_key, check_name, severity from all_exceptions where true"
    params = []
    if table:
        sql += " and table_name = ?"
        params.append(table)
    if check:
        sql += " and check_name = ?"
        params.append(check)
    return con.execute(sql, params).fetchall()


def category(con, order_id: str) -> str:
    return con.execute("select gap_category from reconciliation where order_id = ?", [order_id]).fetchone()[0]


def matched_order(raw: RawCopy, payment_type: str = "boleto", single_item: bool = True) -> str:
    """An order from the fixture that reconciles, paid with one payment of the given type."""
    con = raw.run()
    row = con.execute("""
        select r.order_id from reconciliation r
        where r.is_matched and r.payment_count = 1 and r.main_payment_type = ?
          and (not ? or r.item_count = 1)
          and r.order_status = 'delivered' and not r.has_dq_exception
        order by r.order_id limit 1
    """, [payment_type, single_item]).fetchone()
    assert row, f"fixture has no matched {payment_type} order"
    return row[0]
