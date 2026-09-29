<!-- GENERATED FILE. Edit docs/templates/FINDINGS_MEMO.md.tmpl. Numbers come from reports/metrics.json. -->
# Findings memo: do our sales and payment numbers agree?

**To:** Operations and Finance leads · **Re:** Olist orders 2016-09-04 to 2018-10-17 · **Currency:** Brazilian real (R$, BRL)

## Bottom line

The two systems agree on **98.91%** of 99,441 orders. The 1,079 that do not agree add up to **R$ 166,004.63**, about 1.04% of the R$ 16,008,872.12 customers paid.

Almost all of that money is one problem: **R$ 162,591.95 was paid on 775 orders that have no items recorded.** 98.97% of those orders were canceled or marked unavailable. We cannot see from this data whether those customers were refunded.

Everything else is small and has a clear cause. Only **5 orders (R$ 77.54)** have no explanation.

## What we found

| Cause | Orders | Money | What it means |
|---|---:|---:|---|
| Paid, but no items recorded | 775 | R$ 162,591.95 | Canceled/unavailable orders still show a payment. Refund status unknown. |
| Card interest on installment plans | 232 | R$ 3,050.01 | Customers who split card payments pay extra, on a fixed rate table. The order system does not record it. Normal, but it makes totals disagree. |
| Discounts not recorded on the order | 15 | R$ 123.19 | Customers paid exactly 5% or 10% less than the price. The discount lives only in the payment. |
| Voucher splits | 7 | R$ 17.48 | Card + voucher payments that overshoot the order total. |
| Cent-level rounding | 44 | R$ 1.00 | Harmless. |
| No payment recorded | 1 | R$ 143.46 | Goods recorded, no payment. |
| Unexplained | 5 | R$ 77.54 | Needs a person to look. |

**Customers notice.** Orders that do not reconcile average **2.33 stars**, against **4.11** for orders that do. 61.9% of their reviews are 1 or 2 stars.

**Data you can trust.** We ran 81 automatic checks on every record. 99.58% of rows passed all of them. The main problem: 166 orders show a shipping date *before* the purchase date, which is impossible and most likely a timestamp problem in the carrier feed. No record was deleted; every issue is listed with a reason in `reports/summary.xlsx`.

**Delivery.** 93.2% of delivered orders arrived on time. Late orders average 2.27 stars.

**Planning.** For the next 3 months, plan on about **6,512 orders per month**. The simple "same as last month" rule beat the statistical models we tested (8.7% average error on the last 3 known months). Add a Black Friday uplift for November: last year November was 62.9% above October.

## Top 3 recommendations

1. **Close out the R$ 162,592 paid-no-items orders.** Match the 775 orders against refund records, largest first. 344 orders hold 80% of all unmatched money, so the first pass is short. Any payment without a refund is either owed back to a customer or a revenue booking error.
2. **Record card interest and discounts where the sale is recorded.** Book installment interest as its own revenue line and write discounts onto the order at checkout. Those two causes are 81.5% of the orders where both systems have data but disagree. Fixing them lets Finance and Operations report one number.
3. **Run this reconciliation every day and fix the shipping timestamp feed.** Alert when the match rate drops or a high-severity exception appears, so problems are caught in days, not at month end. Start with the 166 impossible shipping dates.

*Source: `reports/metrics.json`, generated 2026-09-29T07:24:44+00:00 by `run_pipeline.py`. Data: Brazilian E-Commerce Public Dataset by Olist (Kaggle), CC BY-NC-SA 4.0.*
