<!-- GENERATED FILE by src/data_dictionary.py. Edit the descriptions there. -->
# Data dictionary

Every output table and column. Money is in Brazilian real (BRL). Star schema files are in `data/processed/` as both CSV and Parquet. Relationships: see `dashboard/POWERBI_SPEC.md`.

## `fact_orders`

One row per order in the orders table (first copy if an order_id is duplicated).

| Column | Type | Description |
|---|---|---|
| `order_id` | VARCHAR | Order id (32-char hash). Primary key. |
| `customer_id` | VARCHAR | Customer id for this order. Olist issues one customer_id per order. |
| `state_code` | VARCHAR | Customer state, 2 letters. FK to dim_customer_state. UNKNOWN if the customer is missing. |
| `purchase_date_key` | INTEGER | Purchase date as yyyymmdd. FK to dim_date (active relationship). |
| `delivered_date_key` | INTEGER | Delivery-to-customer date as yyyymmdd. FK to dim_date (inactive relationship). Blank if not delivered. |
| `estimated_date_key` | INTEGER | Estimated delivery date as yyyymmdd. |
| `order_status` | VARCHAR | Order status from the source: created, approved, invoiced, processing, shipped, delivered, canceled, unavailable. |
| `payment_type` | VARCHAR | Payment type carrying the largest share of the order value. FK to dim_payment_type. 'none' if no payment. |
| `category_key` | VARCHAR | Portuguese category of the most expensive item. FK to dim_product_category. 'unknown' if none. |
| `order_purchase_timestamp` | TIMESTAMP | When the customer placed the order. |
| `order_approved_at` | TIMESTAMP | When the payment was approved. |
| `order_delivered_carrier_date` | TIMESTAMP | When the order was handed to the carrier. |
| `order_delivered_customer_date` | TIMESTAMP | When the customer received the order. |
| `order_estimated_delivery_date` | TIMESTAMP | Delivery date promised to the customer. |
| `item_count` | BIGINT | Number of item rows for the order (0 if none). |
| `product_value` | DECIMAL(38,2) | Sum of item prices, BRL. |
| `freight_value` | DECIMAL(38,2) | Sum of item freight charges, BRL. |
| `sold_value` | DECIMAL(38,2) | System A total: product_value + freight_value, BRL. |
| `paid_value` | DECIMAL(38,2) | System B total: sum of payment values, BRL. |
| `is_delivered` | BOOLEAN | True if a customer delivery date exists. |
| `is_on_time` | BOOLEAN | True if delivered on or before the estimated date (date level). Blank if not delivered. |
| `delivery_days` | BIGINT | Days from purchase to customer delivery. |
| `review_score` | DOUBLE | Average review score (1 to 5) for the order. Blank if no review. |
| `review_count` | BIGINT | Number of reviews for the order. |
| `is_matched` | BOOLEAN | True if paid and sold agree within the tolerance (R$ 0.01). |
| `gap_category` | VARCHAR | Reconciliation bucket (see fact_reconciliation). |
| `has_dq_exception` | BOOLEAN | True if the order, its items or payments have a high or medium data quality exception. |

## `fact_reconciliation`

One row per order_id found in ANY of orders, order_items or order_payments.

| Column | Type | Description |
|---|---|---|
| `order_id` | VARCHAR | Order id. Primary key. |
| `state_code` | VARCHAR | Customer state. FK to dim_customer_state. |
| `purchase_date_key` | INTEGER | Purchase date as yyyymmdd. FK to dim_date. |
| `payment_type` | VARCHAR | Main payment type. FK to dim_payment_type. |
| `category_key` | VARCHAR | Category of the most expensive item. FK to dim_product_category. |
| `in_orders` | BOOLEAN | True if the order_id exists in the orders table (False = orphan items/payments). |
| `order_status` | VARCHAR | Order status. |
| `item_count` | BIGINT | Item rows in System A. Blank if none. |
| `payment_count` | BIGINT | Payment rows in System B. Blank if none. |
| `payment_types` | VARCHAR | All payment types used, joined with '+', e.g. credit_card+voucher. |
| `max_installments` | INTEGER | Highest installment count across the order's payments. |
| `has_voucher` | BOOLEAN | True if any payment is a voucher. |
| `product_value` | DECIMAL(38,2) | Sum of item prices, BRL. |
| `freight_value` | DECIMAL(38,2) | Sum of freight, BRL. |
| `expected_total` | DECIMAL(38,2) | System A: product_value + freight_value, BRL. Blank if no items. |
| `paid_total` | DECIMAL(38,2) | System B: sum of payment_value, BRL. Blank if no payments. |
| `gap` | DECIMAL(38,2) | paid_total - expected_total (missing side counts as 0), BRL. Positive = customer paid more. |
| `abs_gap` | DECIMAL(38,2) | Absolute value of gap, BRL. |
| `gap_pct` | DOUBLE | gap / expected_total x 100. Blank if a side is missing. |
| `paid_to_sold_ratio` | DOUBLE | paid_total / expected_total, 4 decimals. Used to find the card interest rate table. |
| `is_matched` | BOOLEAN | True if abs_gap <= R$ 0.01 and both sides exist. |
| `gap_category` | VARCHAR | Bucket: matched, rounding, voucher_related, installment_interest, untracked_discount, missing_items, missing_payment, orphan_no_order, empty_order, unexplained. |
| `severity` | VARCHAR | high / medium / low for unmatched orders; blank if matched. |
| `has_dq_exception` | BOOLEAN | True if a high/medium data quality exception touches this order. |
| `gap_rank_in_month` | BIGINT | DENSE_RANK of abs_gap within the purchase month (1 = largest). Unmatched only. |
| `gap_rank_in_state` | BIGINT | DENSE_RANK of abs_gap within the customer state (1 = largest). Unmatched only. |
| `cumulative_gap_share` | DOUBLE | Running share (0 to 1) of all unmatched money, largest gaps first. Pareto analysis. |

## `fact_exceptions`

One row per exception from data quality checks or reconciliation. Bad rows are listed here, never deleted.

| Column | Type | Description |
|---|---|---|
| `exception_id` | BIGINT | Exception id. Primary key. |
| `source` | VARCHAR | data_quality or reconciliation. |
| `table_name` | VARCHAR | Table the record came from (orders, order_items, ..., or reconciliation). |
| `record_id` | BIGINT | Row number of the record in its raw file (1 = first data row). Stable id even when keys are duplicated. |
| `record_key` | VARCHAR | Natural key of the record, e.g. order_id|order_item_id. |
| `order_id` | VARCHAR | Order id when the record belongs to an order, else blank. |
| `check_name` | VARCHAR | Check that failed, e.g. duplicate_key, carrier_before_purchase, recon_missing_items. |
| `reason` | VARCHAR | Plain-language reason with the offending values. |
| `severity` | VARCHAR | high = money or counts wrong if trusted; medium = suspicious; low = informational. |
| `purchase_date_key` | INTEGER | Purchase date of the related order. FK to dim_date. |
| `state_code` | VARCHAR | Customer state of the related order. FK to dim_customer_state. |

## `dim_date`

One row per calendar day from the first purchase to the last delivery or estimate.

| Column | Type | Description |
|---|---|---|
| `date_key` | INTEGER | yyyymmdd integer. Primary key. |
| `date` | DATE | Calendar date. Mark as date table in Power BI. |
| `year` | BIGINT | Year. |
| `quarter` | BIGINT | Quarter 1 to 4. |
| `month` | BIGINT | Month 1 to 12. |
| `month_name` | VARCHAR | Month name. |
| `year_month` | VARCHAR | yyyy-mm text, for slicers. |
| `month_start` | DATE | First day of the month. |
| `iso_week` | BIGINT | ISO week number. |
| `day_of_week` | BIGINT | ISO day of week, 1 = Monday. |
| `day_name` | VARCHAR | Day name. |
| `is_weekend` | BOOLEAN | True on Saturday and Sunday. |

## `dim_customer_state`

The 27 Brazilian federative units plus UNKNOWN.

| Column | Type | Description |
|---|---|---|
| `state_code` | VARCHAR | 2-letter code. Primary key. |
| `state_name` | VARCHAR | State name. |
| `region` | VARCHAR | IBGE macro-region: North, Northeast, Center-West, Southeast, South. |

## `dim_payment_type`

Every payment type seen in the data plus 'none'.

| Column | Type | Description |
|---|---|---|
| `payment_type` | VARCHAR | Payment type. Primary key. |
| `description` | VARCHAR | Plain-language description. |
| `is_card` | BOOLEAN | True for credit and debit card. |

## `dim_product_category`

Product categories with English names from the translation file.

| Column | Type | Description |
|---|---|---|
| `category_key` | VARCHAR | Portuguese category name as in the source, or 'unknown'. Primary key. |
| `category_name_pt` | VARCHAR | Portuguese name (blank for unknown). |
| `category_name_en` | VARCHAR | English name; falls back to the Portuguese name when no translation exists. |
| `has_translation` | BOOLEAN | False for categories missing from the translation file. |

## `data/processed/forecast_monthly.csv`

Monthly orders: actuals, holdout predictions per model, and the forecast.

| Column | Type | Description |
|---|---|---|
| `month` | VARCHAR | yyyy-mm. |
| `series` | VARCHAR | 'actual' or the model name. |
| `row_type` | VARCHAR | actual, holdout (prediction for a known month) or forecast (future month). |
| `orders` | BIGINT | Order count (actual or predicted). |
| `used_in_model` | BOOLEAN | True if the month is inside the complete-month window used for training/holdout. |
| `month_start` | DATE | First day of the month (date). |

## `reports/reconciliation_summary.csv`

One row per reconciliation bucket.

| Column | Type | Description |
|---|---|---|
| `gap_category` | VARCHAR | Bucket. |
| `severity` | VARCHAR | Severity rule for the bucket. |
| `orders` | BIGINT | Orders in the bucket. |
| `share_of_orders_pct` | DOUBLE | Orders in bucket / all orders x 100. |
| `sold_brl` | DOUBLE | Sum of expected_total, BRL. |
| `paid_brl` | DOUBLE | Sum of paid_total, BRL. |
| `net_gap_brl` | DOUBLE | Sum of gap, BRL. |
| `abs_gap_brl` | DOUBLE | Sum of abs_gap, BRL. |
| `rule` | VARCHAR | The rule that puts an order in this bucket. |
| `evidence` | VARCHAR | Where the rule comes from. |
| `action` | VARCHAR | What the business should do. |

## `reports/exceptions_summary.csv`

Exceptions grouped by source, table, check and severity.

| Column | Type | Description |
|---|---|---|
| `source` | VARCHAR | data_quality or reconciliation. |
| `table_name` | VARCHAR | Table. |
| `check_name` | VARCHAR | Check. |
| `severity` | VARCHAR | Severity. |
| `exceptions` | BIGINT | Exception rows. |
| `distinct_records` | BIGINT | Distinct record keys. |

## `reports/evidence/*.csv`

One file per evidence query in `sql/reconciliation/04_evidence.sql`. Each file is the data behind a reconciliation bucket rule: `rounding_by_item_count`, `interest_rate_card`, `interest_by_installments`, `discount_share_of_price`, `missing_items_by_status`, `sequence_gap_orders_reconcile`, `voucher_orders`.

## `reports/metrics.json`

Every number used in README.md, reports/FINDINGS_MEMO.md and NOTES.md. Top-level sections: `dataset`, `data_quality`, `reconciliation`, `exceptions`, `kpis`, `forecast`, `star_schema_rows`. Percentages are 0 to 100, money is BRL.
