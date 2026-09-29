"""Failure injection: put one known bad record into a copy of the data, prove the right check catches it."""
from __future__ import annotations

from conftest import category, exceptions, matched_order

GHOST = "ffffffffffffffffffffffffffffffff"


def test_clean_fixture_has_no_high_severity_type_or_key_errors(clean_run):
    bad = clean_run.execute("""
        select count(*) from dq_exceptions
        where check_name in ('duplicate_key', 'type_mismatch', 'required_null', 'orphan_foreign_key')
          and severity = 'high'
    """).fetchone()[0]
    assert bad == 0


def test_duplicate_order_is_caught(raw):
    order = raw.read("orders")[0]
    raw.append("orders", dict(order))
    con = raw.run()
    hits = exceptions(con, "orders", "duplicate_key")
    assert [(h[1], h[3]) for h in hits] == [(order["order_id"], "high")]
    # the duplicate header must not double the order in the reconciliation
    assert con.execute("select count(*) from reconciliation where order_id = ?", [order["order_id"]]).fetchone()[0] == 1


def test_duplicate_payment_is_caught_and_breaks_reconciliation(raw):
    order_id = matched_order(raw, "boleto")
    pay = next(p for p in raw.read("order_payments") if p["order_id"] == order_id)
    raw.append("order_payments", dict(pay))
    con = raw.run()
    assert exceptions(con, "order_payments", "duplicate_key")
    assert category(con, order_id) == "unexplained"


def test_orphan_payment_is_caught(raw):
    raw.append("order_payments", {"order_id": GHOST, "payment_sequential": "1", "payment_type": "boleto",
                                  "payment_installments": "1", "payment_value": "99.90"})
    con = raw.run()
    hits = exceptions(con, "order_payments", "orphan_foreign_key")
    assert len(hits) == 1 and hits[0][1].startswith(GHOST) and hits[0][3] == "high"
    assert category(con, GHOST) == "orphan_no_order"


def test_orphan_item_is_caught(raw):
    item = dict(raw.read("order_items")[0], order_id=GHOST)
    raw.append("order_items", item)
    con = raw.run()
    assert exceptions(con, "order_items", "orphan_foreign_key")
    assert category(con, GHOST) == "orphan_no_order"


def test_negative_price_is_caught(raw):
    item = raw.read("order_items")[0]
    raw.update("order_items", {"order_id": item["order_id"], "order_item_id": item["order_item_id"]}, price="-5.00")
    con = raw.run()
    hits = exceptions(con, "order_items", "non_positive_price")
    assert [(h[1], h[3]) for h in hits] == [(f"{item['order_id']}|{item['order_item_id']}", "high")]


def test_zero_price_is_caught(raw):
    item = raw.read("order_items")[1]
    raw.update("order_items", {"order_id": item["order_id"], "order_item_id": item["order_item_id"]}, price="0")
    con = raw.run()
    assert len(exceptions(con, "order_items", "non_positive_price")) == 1


def test_approved_before_purchase_is_caught(raw):
    order = next(o for o in raw.read("orders") if o["order_approved_at"])
    raw.update("orders", {"order_id": order["order_id"]}, order_approved_at="2010-01-01 00:00:00")
    con = raw.run()
    hits = exceptions(con, "orders", "approved_before_purchase")
    assert [(h[1], h[3]) for h in hits] == [(order["order_id"], "high")]


def test_delivered_before_purchase_is_caught(raw):
    order = next(o for o in raw.read("orders") if o["order_delivered_customer_date"])
    raw.update("orders", {"order_id": order["order_id"]}, order_delivered_customer_date="2010-01-01 00:00:00")
    con = raw.run()
    assert [h[1] for h in exceptions(con, "orders", "delivered_before_purchase")] == [order["order_id"]]


def test_payment_mismatch_is_caught(raw):
    order_id = matched_order(raw, "boleto")
    pay = next(p for p in raw.read("order_payments") if p["order_id"] == order_id)
    raw.update("order_payments", {"order_id": order_id, "payment_sequential": pay["payment_sequential"]},
               payment_value=f"{float(pay['payment_value']) + 37:.2f}")
    con = raw.run()
    gap, cat, sev = con.execute(
        "select gap, gap_category, severity from reconciliation where order_id = ?", [order_id]).fetchone()
    assert float(gap) == 37.0 and cat == "unexplained" and sev == "high"
    assert exceptions(con, "reconciliation", "recon_unexplained")


def test_bad_type_is_caught_not_crashed(raw):
    item = raw.read("order_items")[0]
    raw.update("order_items", {"order_id": item["order_id"], "order_item_id": item["order_item_id"]}, price="abc")
    con = raw.run()
    hits = exceptions(con, "order_items", "type_mismatch")
    assert len(hits) == 1 and hits[0][3] == "high"


def test_unknown_status_and_payment_type_are_caught(raw):
    order = raw.read("orders")[0]
    raw.update("orders", {"order_id": order["order_id"]}, order_status="teleported")
    pay = raw.read("order_payments")[0]
    raw.update("order_payments", {"order_id": pay["order_id"], "payment_sequential": pay["payment_sequential"]},
               payment_type="bitcoin")
    con = raw.run()
    assert len(exceptions(con, "orders", "allowed_values")) == 1
    assert len(exceptions(con, "order_payments", "allowed_values")) == 1


def test_required_null_is_caught(raw):
    order = raw.read("orders")[0]
    raw.update("orders", {"order_id": order["order_id"]}, customer_id="")
    con = raw.run()
    assert len(exceptions(con, "orders", "required_null")) == 1


def test_review_for_unknown_order_is_caught(raw):
    review = dict(raw.read("order_reviews")[0], review_id="r" * 32, order_id=GHOST)
    raw.append("order_reviews", review)
    con = raw.run()
    hits = exceptions(con, "order_reviews", "review_unknown_order")
    assert len(hits) == 1 and hits[0][3] == "high"


def test_payment_sequence_gap_is_low_severity(raw):
    order_id = matched_order(raw, "boleto")
    raw.update("order_payments", {"order_id": order_id}, payment_sequential="3")
    con = raw.run()
    hits = exceptions(con, "order_payments", "payment_sequence_gap")
    assert len(hits) == 1 and hits[0][3] == "low"


def test_bad_rows_are_never_deleted(raw):
    """Quarantined rows stay in staging and in the exceptions table."""
    item = raw.read("order_items")[0]
    raw.update("order_items", {"order_id": item["order_id"], "order_item_id": item["order_item_id"]}, price="-1")
    con = raw.run()
    n_raw = con.execute("select count(*) from raw_order_items").fetchone()[0]
    n_stg = con.execute("select count(*) from stg_order_items").fetchone()[0]
    n_clean = con.execute("select count(*) from clean_order_items").fetchone()[0]
    assert n_raw == n_stg == len(raw.read("order_items"))
    assert n_clean == n_raw - 1
