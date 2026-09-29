"""Nothing silently dropped: every input row is either clean or in the exceptions table."""
from __future__ import annotations

import pytest

from conftest import FIXTURES, RawCopy
from src.config import RAW_FILES

TABLES = list(RAW_FILES)


def _check_completeness(con, csv_rows: dict[str, int]) -> None:
    for t in TABLES:
        raw = con.execute(f"select count(*) from raw_{t}").fetchone()[0]
        clean = con.execute(f"select count(*) from clean_{t}").fetchone()[0]
        quarantined = con.execute(
            "select count(*) from dq_row_status where table_name = ? and row_status = 'quarantined'", [t]).fetchone()[0]
        flagged = con.execute(
            "select count(distinct record_id) from dq_exceptions where table_name = ?", [t]).fetchone()[0]
        no_exception = con.execute(
            "select count(*) from dq_row_status where table_name = ? and row_status = 'clean'", [t]).fetchone()[0]

        assert raw == csv_rows[t], f"{t}: loader lost rows"
        assert raw == clean + quarantined, f"{t}: usable + quarantined != input"
        assert raw == no_exception + flagged, f"{t}: rows without exceptions + rows with exceptions != input"

    # Reconciliation: every order_id from any source appears exactly once,
    # and is either matched or has exactly one reconciliation exception.
    universe = con.execute("""
        select count(*) from (
            select order_id from raw_orders union select order_id from raw_order_items
            union select order_id from raw_order_payments)
    """).fetchone()[0]
    recon, distinct_ids, matched = con.execute(
        "select count(*), count(distinct order_id), count(*) filter (where is_matched) from reconciliation").fetchone()
    recon_exc = con.execute("select count(*) from recon_exceptions").fetchone()[0]
    assert recon == distinct_ids == universe
    assert matched + recon_exc == universe


def test_completeness_on_clean_fixture(clean_run):
    counts = {t: len(RawCopy(FIXTURES).read(t)) for t in TABLES}
    _check_completeness(clean_run, counts)


@pytest.mark.parametrize("corruption", ["duplicate", "orphan", "negative", "bad_type"])
def test_completeness_holds_after_corruption(raw, corruption):
    item = raw.read("order_items")[0]
    key = {"order_id": item["order_id"], "order_item_id": item["order_item_id"]}
    if corruption == "duplicate":
        raw.append("order_items", dict(item))
    elif corruption == "orphan":
        raw.append("order_payments", {"order_id": "0" * 32, "payment_sequential": "1", "payment_type": "boleto",
                                      "payment_installments": "1", "payment_value": "10.00"})
    elif corruption == "negative":
        raw.update("order_items", key, price="-3")
    elif corruption == "bad_type":
        raw.update("order_items", key, freight_value="n/a")
    con = raw.run()
    _check_completeness(con, {t: len(raw.read(t)) for t in TABLES})


def test_exception_rows_have_required_fields(clean_run):
    bad = clean_run.execute("""
        select count(*) from all_exceptions
        where table_name is null or record_key is null or check_name is null or reason is null
           or severity not in ('high', 'medium', 'low')
    """).fetchone()[0]
    assert bad == 0
