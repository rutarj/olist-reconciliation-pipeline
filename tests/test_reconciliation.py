"""Reconciliation buckets: build an order that should land in each bucket and check it does."""
from __future__ import annotations

from conftest import category

NEW = "a" * 32


def _new_order(raw, prices: list[tuple[str, str]], payments: list[tuple[str, str, str]], status="delivered"):
    """Add a fresh order with the given (price, freight) items and (type, installments, value) payments."""
    template = raw.read("orders")[0]
    raw.append("orders", dict(template, order_id=NEW, order_status=status))
    item_tpl = raw.read("order_items")[0]
    raw.write("order_items", raw.read("order_items") + [
        dict(item_tpl, order_id=NEW, order_item_id=str(i + 1), price=p, freight_value=f)
        for i, (p, f) in enumerate(prices)])
    raw.write("order_payments", raw.read("order_payments") + [
        {"order_id": NEW, "payment_sequential": str(i + 1), "payment_type": t,
         "payment_installments": n, "payment_value": v}
        for i, (t, n, v) in enumerate(payments)])


def test_exact_match(raw):
    _new_order(raw, [("100.00", "10.00")], [("boleto", "1", "110.00")])
    assert category(raw.run(), NEW) == "matched"


def test_one_cent_is_within_tolerance(raw):
    _new_order(raw, [("100.00", "10.00")], [("boleto", "1", "110.01")])
    assert category(raw.run(), NEW) == "matched"


def test_two_cents_on_one_item_is_not_rounding(raw):
    _new_order(raw, [("100.00", "10.00")], [("boleto", "1", "110.02")])
    assert category(raw.run(), NEW) == "unexplained"


def test_rounding_on_multi_item_order(raw):
    _new_order(raw, [("33.33", "1.00")] * 3, [("boleto", "1", "103.01")])  # 3 items, 0.02 gap
    assert category(raw.run(), NEW) == "rounding"


def test_installment_interest(raw):
    _new_order(raw, [("100.00", "0.00")], [("credit_card", "3", "104.61")])  # the 3x rate from the data
    assert category(raw.run(), NEW) == "installment_interest"


def test_overpaid_single_installment_is_not_interest(raw):
    _new_order(raw, [("100.00", "0.00")], [("credit_card", "1", "104.61")])
    assert category(raw.run(), NEW) == "unexplained"


def test_voucher_related(raw):
    _new_order(raw, [("50.00", "10.00")], [("credit_card", "1", "40.00"), ("voucher", "1", "22.00")])
    assert category(raw.run(), NEW) == "voucher_related"


def test_untracked_discount_5_and_10_percent(raw):
    _new_order(raw, [("200.00", "20.00")], [("debit_card", "1", "210.00")])  # 5% of 200 missing
    assert category(raw.run(), NEW) == "untracked_discount"


def test_random_underpayment_is_unexplained(raw):
    _new_order(raw, [("200.00", "20.00")], [("debit_card", "1", "187.00")])  # 33 missing = 16.5%
    assert category(raw.run(), NEW) == "unexplained"


def test_missing_payment(raw):
    _new_order(raw, [("80.00", "5.00")], [])
    con = raw.run()
    assert category(con, NEW) == "missing_payment"
    assert con.execute("select severity from reconciliation where order_id = ?", [NEW]).fetchone()[0] == "high"


def test_missing_items_severity_depends_on_status(raw):
    _new_order(raw, [], [("boleto", "1", "50.00")], status="canceled")
    con = raw.run()
    assert con.execute("select gap_category, severity from reconciliation where order_id = ?",
                       [NEW]).fetchone() == ("missing_items", "medium")


def test_missing_items_on_open_order_is_high(raw):
    _new_order(raw, [], [("boleto", "1", "50.00")], status="shipped")
    con = raw.run()
    assert con.execute("select severity from reconciliation where order_id = ?", [NEW]).fetchone()[0] == "high"


def test_every_bucket_in_fixture(clean_run):
    cats = {r[0] for r in clean_run.execute("select distinct gap_category from reconciliation").fetchall()}
    assert {"matched", "rounding", "installment_interest", "voucher_related", "untracked_discount",
            "missing_items", "missing_payment", "unexplained"} <= cats


def test_ranking_windows(clean_run):
    top = clean_run.execute("""
        select abs_gap, cumulative_gap_share from reconciliation_ranked order by overall_rank
    """).fetchall()
    gaps = [float(g) for g, _ in top]
    assert gaps == sorted(gaps, reverse=True)
    assert abs(float(top[-1][1]) - 1.0) < 1e-6
    assert clean_run.execute(
        "select min(gap_rank_in_month) from reconciliation_ranked").fetchone()[0] == 1
