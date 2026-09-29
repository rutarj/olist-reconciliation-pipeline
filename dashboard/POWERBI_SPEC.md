# Power BI build spec

Exact steps to rebuild `reports/dashboard.html` as a Power BI report on the star schema in `data/processed/`.
Run `python run_pipeline.py` first so the files exist.

## 1. Load the data

**Get Data → Parquet** (preferred: types are kept) for each file below. CSV works too; then set the types in the table below by hand.

| Table | File | Grain |
|---|---|---|
| fact_orders | `data/processed/fact_orders.parquet` | 1 row per order |
| fact_reconciliation | `data/processed/fact_reconciliation.parquet` | 1 row per order_id seen in any system |
| fact_exceptions | `data/processed/fact_exceptions.parquet` | 1 row per exception (data quality + reconciliation) |
| dim_date | `data/processed/dim_date.parquet` | 1 row per day |
| dim_customer_state | `data/processed/dim_customer_state.parquet` | 1 row per Brazilian state (+ UNKNOWN) |
| dim_payment_type | `data/processed/dim_payment_type.parquet` | 1 row per payment type (+ none) |
| dim_product_category | `data/processed/dim_product_category.parquet` | 1 row per category (+ unknown) |
| forecast_monthly | `data/processed/forecast_monthly.csv` | 1 row per month and series |

Power Query type fixes:
- `dim_date[date]`, `forecast_monthly[month_start]`: Date.
- All `*_date_key` columns: Whole number.
- Money columns (`sold_value`, `paid_value`, `expected_total`, `paid_total`, `gap`, `abs_gap`, `product_value`, `freight_value`): Fixed decimal number. Format as currency **R$ (Portuguese, Brazil)**. The currency is Brazilian real, not dollars.
- `gap_pct`, `paid_to_sold_ratio`, `cumulative_gap_share`: Decimal number.

Then **Table tools → Mark as date table** on `dim_date`, date column `dim_date[date]`.

## 2. Relationships (Model view)

All are many-to-one, single direction (dimension filters fact), active unless noted.

| From (many) | To (one) | Notes |
|---|---|---|
| fact_orders[purchase_date_key] | dim_date[date_key] | active |
| fact_orders[delivered_date_key] | dim_date[date_key] | **inactive**; use with `USERELATIONSHIP` for "by delivery date" views |
| fact_orders[state_code] | dim_customer_state[state_code] | |
| fact_orders[payment_type] | dim_payment_type[payment_type] | |
| fact_orders[category_key] | dim_product_category[category_key] | |
| fact_reconciliation[purchase_date_key] | dim_date[date_key] | |
| fact_reconciliation[state_code] | dim_customer_state[state_code] | |
| fact_reconciliation[payment_type] | dim_payment_type[payment_type] | |
| fact_reconciliation[category_key] | dim_product_category[category_key] | |
| fact_exceptions[purchase_date_key] | dim_date[date_key] | blank for exceptions not tied to an order (reviews, products) |
| fact_exceptions[state_code] | dim_customer_state[state_code] | |

Do not relate the facts to each other. Every fact shares the same dimensions, so slicers filter them all together.
`forecast_monthly` stays standalone (it is monthly and already aggregated).

## 3. DAX measures

Create a table called `_Measures` (Enter data → one empty column → load) and add these measures to it.

```DAX
Orders Reconciled =
COUNTROWS ( fact_reconciliation )
```

```DAX
Unmatched Orders =
CALCULATE ( COUNTROWS ( fact_reconciliation ), fact_reconciliation[is_matched] = FALSE () )
```

```DAX
Match Rate % =
DIVIDE ( [Orders Reconciled] - [Unmatched Orders], [Orders Reconciled] )
```
Format: Percentage, 2 decimals.

```DAX
Total Abs Gap (BRL) =
CALCULATE ( SUM ( fact_reconciliation[abs_gap] ), fact_reconciliation[is_matched] = FALSE () )
```
Format: Currency R$, 2 decimals.

```DAX
Avg Gap per Unmatched Order (BRL) =
DIVIDE ( [Total Abs Gap (BRL)], [Unmatched Orders] )
```

```DAX
Paid With No Items (BRL) =
CALCULATE (
    SUM ( fact_reconciliation[paid_total] ),
    fact_reconciliation[gap_category] = "missing_items"
)
```

```DAX
High Severity Exceptions =
CALCULATE ( COUNTROWS ( fact_exceptions ), fact_exceptions[severity] = "high" )
```

```DAX
On-Time Delivery % =
DIVIDE (
    CALCULATE ( COUNTROWS ( fact_orders ), fact_orders[is_on_time] = TRUE () ),
    CALCULATE ( COUNTROWS ( fact_orders ), fact_orders[is_delivered] = TRUE () )
)
```

```DAX
Match Rate MoM Change (pp) =
VAR CurrentRate = [Match Rate %]
VAR PreviousRate = CALCULATE ( [Match Rate %], DATEADD ( dim_date[date], -1, MONTH ) )
RETURN
    IF ( NOT ISBLANK ( PreviousRate ), ( CurrentRate - PreviousRate ) * 100 )
```
Format: Decimal, 2 places, suffix " pp".

```DAX
Avg Review Score (Unmatched) =
CALCULATE ( AVERAGE ( fact_orders[review_score] ), fact_orders[is_matched] = FALSE () )
```

```DAX
Avg Review Score (Matched) =
CALCULATE ( AVERAGE ( fact_orders[review_score] ), fact_orders[is_matched] = TRUE () )
```

Check after building: with no slicers, every measure must equal the value of the same name in `reports/metrics.json`
(`reconciliation.match_rate_pct`, `reconciliation.abs_gap_brl`, `kpis.delivery.on_time_rate_pct`, ...). If one does not, a relationship or type is wrong.

## 4. Pages and visuals

Canvas 16:9. One row of slicers at the top of every page: `dim_date[year_month]` (dropdown, multi-select),
`dim_customer_state[region]`, `dim_payment_type[payment_type]`. Sync slicers across pages 1 to 4 (View → Sync slicers).

### Page 1: Overview

| Visual | Fields | Settings |
|---|---|---|
| Card | `Match Rate %` | title "Match rate" |
| Card | `Unmatched Orders` | |
| Card | `Total Abs Gap (BRL)` | |
| Card | `Paid With No Items (BRL)` | title "Paid, no items (refund exposure)" |
| Card | `On-Time Delivery %` | |
| Line chart | X: `dim_date[month_start]` (continuous), Y: `Match Rate %` | filter `dim_date[year_month]` between 2017-01 and 2018-08 (complete months) |
| Clustered bar | Y: `fact_reconciliation[gap_category]`, X: `Total Abs Gap (BRL)` | filter `is_matched = False`, sort by X descending, data labels on |
| Clustered bar | Y: `fact_reconciliation[gap_category]`, X: `Unmatched Orders` | sort descending, data labels on |

### Page 2: Reconciliation detail

| Visual | Fields | Settings |
|---|---|---|
| Matrix | Rows: `fact_reconciliation[gap_category]`, Columns: `fact_reconciliation[severity]`, Values: `Unmatched Orders`, `Total Abs Gap (BRL)` | filter `is_matched = False` |
| Decomposition tree | Analyze: `Total Abs Gap (BRL)`, Explain by: `gap_category`, `dim_customer_state[region]`, `dim_customer_state[state_name]`, `dim_payment_type[payment_type]`, `fact_reconciliation[order_status]` | |
| Table | `order_id`, `order_status`, `gap_category`, `severity`, `expected_total`, `paid_total`, `gap`, `gap_rank_in_month`, `cumulative_gap_share` | filter `is_matched = False`, sort by `abs_gap` descending, conditional format background on `severity` (high red, medium orange, low yellow) |
| Clustered column | X: `fact_reconciliation[max_installments]`, Y: Median of `fact_reconciliation[gap_pct]` | filter `gap_category = installment_interest`; this is the card-interest evidence chart |

### Page 3: Data quality

| Visual | Fields | Settings |
|---|---|---|
| Card | `High Severity Exceptions` | |
| Card | Count of `fact_exceptions[exception_id]` | title "All exceptions" |
| Clustered bar | Y: `fact_exceptions[check_name]`, X: Count of `exception_id`, Legend: `fact_exceptions[severity]` | sort descending |
| Stacked column | X: `dim_date[month_start]`, Y: Count of `exception_id`, Legend: `fact_exceptions[source]` | |
| Table | `source`, `table_name`, `record_key`, `check_name`, `severity`, `reason` | slicer on `severity` next to it |

### Page 4: Operations and customers

| Visual | Fields | Settings |
|---|---|---|
| Card | `On-Time Delivery %` | |
| Card | `Avg Review Score (Matched)` | |
| Card | `Avg Review Score (Unmatched)` | |
| Filled map | Location: `dim_customer_state[state_name]` (data category: State or Province), Color saturation: `Unmatched Orders` | tooltip: `Match Rate %`, `Total Abs Gap (BRL)` |
| Clustered bar | Y: `dim_product_category[category_name_en]`, X: `Unmatched Orders` | Top N filter = 10 by `Unmatched Orders`; filter `fact_reconciliation[item_count]` is not blank |
| Clustered column | X: `fact_orders[is_on_time]`, Y: Average of `fact_orders[review_score]` | the late-delivery vs review evidence |

### Page 5: Forecast

| Visual | Fields | Settings |
|---|---|---|
| Line chart | X: `forecast_monthly[month_start]`, Y: Sum of `forecast_monthly[orders]`, Legend: `forecast_monthly[series]` | filter `used_in_model = True` or `row_type = forecast`; style the forecast series dashed |
| Table | from `reports/metrics.json` → `forecast.scores` (paste as Enter data): `model`, `kind`, `holdout_mape_pct` | text box underneath stating which model won and that a naive baseline is kept if it wins |

## 5. Before you publish

- Numbers match `reports/metrics.json` with no slicers applied.
- Every currency field shows R$, not $.
- Footer text box on each page: "Data: Brazilian E-Commerce Public Dataset by Olist (Kaggle), CC BY-NC-SA 4.0."
