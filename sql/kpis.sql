-- KPI queries on the star schema. Each block starts with "-- name: <kpi>" and is run by
-- src/kpis.py. Results go to reports/metrics.json, the Excel report and the HTML dashboard.

-- name: headline
select
    count(*)                                                           as orders_total,
    count(*) filter (where in_orders)                                  as orders_in_orders_table,
    count(*) filter (where expected_total is not null and paid_total is not null) as orders_in_both_systems,
    count(*) filter (where is_matched)                                 as orders_matched,
    count(*) filter (where not is_matched)                             as orders_unmatched,
    count(*) filter (where not is_matched and expected_total is not null and paid_total is not null)
                                                                       as orders_value_mismatch,
    round(100.0 * count(*) filter (where is_matched) / count(*), 4)    as match_rate_pct,
    round(100.0 * count(*) filter (where is_matched)
          / count(*) filter (where expected_total is not null and paid_total is not null), 4)
                                                                       as match_rate_both_systems_pct,
    sum(expected_total)                                                as sold_brl,
    sum(paid_total)                                                    as paid_brl,
    sum(abs_gap) filter (where not is_matched)                         as abs_gap_brl,
    sum(gap) filter (where not is_matched)                             as net_gap_brl,
    round(avg(abs_gap) filter (where not is_matched), 2)               as avg_abs_gap_brl,
    sum(abs_gap) filter (where not is_matched and expected_total is not null and paid_total is not null)
                                                                       as value_mismatch_abs_gap_brl,
    round(avg(abs_gap) filter (where not is_matched and expected_total is not null and paid_total is not null), 2)
                                                                       as value_mismatch_avg_abs_gap_brl,
    count(*) filter (where gap_category = 'unexplained')               as orders_unexplained,
    sum(abs_gap) filter (where gap_category = 'unexplained')           as unexplained_abs_gap_brl,
    count(*) filter (where severity = 'high')                          as orders_high_severity,
    sum(abs_gap) filter (where severity = 'high')                      as high_severity_abs_gap_brl
from fact_reconciliation;

-- name: gap_by_category
select
    gap_category,
    string_agg(distinct severity, '/' order by severity) as severity,
    count(*)                                             as orders,
    round(100.0 * count(*) / sum(count(*)) over (), 4)   as share_of_orders_pct,
    sum(abs_gap)                                         as abs_gap_brl,
    sum(gap)                                             as net_gap_brl,
    round(avg(abs_gap), 2)                               as avg_abs_gap_brl,
    round(100.0 * sum(abs_gap) / sum(sum(abs_gap) filter (where not is_matched)) over (), 2)
                                                         as share_of_unmatched_gap_pct
from fact_reconciliation
where not is_matched
group by gap_category
order by abs_gap_brl desc;

-- name: pareto
-- How many of the unmatched orders hold 80% of the unmatched money?
select
    count(*) filter (where cumulative_gap_share <= 0.8) + 1 as orders_for_80pct_of_gap,
    count(*)                                                as unmatched_orders
from fact_reconciliation
where not is_matched;

-- name: exceptions_by_check
select source, table_name, check_name, severity, count(*) as exceptions
from fact_exceptions
group by source, table_name, check_name, severity
order by case severity when 'high' then 1 when 'medium' then 2 else 3 end, exceptions desc;

-- name: exceptions_by_severity
select severity, count(*) as exceptions,
       count(*) filter (where source = 'data_quality')   as data_quality,
       count(*) filter (where source = 'reconciliation') as reconciliation
from fact_exceptions
group by severity
order by case severity when 'high' then 1 when 'medium' then 2 else 3 end;

-- name: row_status
select table_name,
       count(*)                                           as rows_in,
       count(*) filter (where row_status = 'clean')       as clean,
       count(*) filter (where row_status = 'warning')     as warning,
       count(*) filter (where row_status = 'quarantined') as quarantined
from dq_row_status
group by table_name
order by rows_in desc;

-- name: monthly
with rec as (
    select d.month_start,
           count(*)                                                as orders,
           count(*) filter (where r.is_matched)                    as matched,
           count(*) filter (where not r.is_matched)                as unmatched,
           coalesce(sum(r.abs_gap) filter (where not r.is_matched), 0) as abs_gap_brl,
           sum(r.expected_total)                                   as sold_brl
    from fact_reconciliation r
    join dim_date d on d.date_key = r.purchase_date_key
    group by d.month_start
),
dlv as (
    select d.month_start,
           count(*) filter (where f.is_delivered)                  as delivered,
           count(*) filter (where f.is_on_time)                    as on_time
    from fact_orders f
    join dim_date d on d.date_key = f.purchase_date_key
    group by d.month_start
),
exc as (
    select d.month_start, count(*) as exceptions
    from fact_exceptions e
    join dim_date d on d.date_key = e.purchase_date_key
    group by d.month_start
)
select
    strftime(rec.month_start, '%Y-%m')                              as month,
    rec.orders,
    rec.matched,
    rec.unmatched,
    round(100.0 * rec.matched / rec.orders, 2)                      as match_rate_pct,
    rec.abs_gap_brl,
    rec.sold_brl,
    coalesce(exc.exceptions, 0)                                     as exceptions,
    dlv.delivered,
    round(100.0 * dlv.on_time / nullif(dlv.delivered, 0), 2)        as on_time_rate_pct
from rec
left join dlv using (month_start)
left join exc using (month_start)
order by rec.month_start;

-- name: top_states
-- States ranked by unmatched orders. Rate is shown so small states are not over-read.
select
    s.state_code,
    s.state_name,
    s.region,
    count(*)                                              as orders,
    count(*) filter (where not r.is_matched)              as unmatched,
    round(100.0 * count(*) filter (where not r.is_matched) / count(*), 2) as unmatched_rate_pct,
    coalesce(sum(r.abs_gap) filter (where not r.is_matched), 0) as abs_gap_brl,
    rank() over (order by count(*) filter (where not r.is_matched) desc) as rank_by_unmatched
from fact_reconciliation r
join dim_customer_state s using (state_code)
group by all
order by unmatched desc, orders desc;

-- name: top_categories
-- Only orders that have items: an order with no items has no category to blame.
select
    c.category_name_en,
    count(*)                                              as orders,
    count(*) filter (where not r.is_matched)              as unmatched,
    round(100.0 * count(*) filter (where not r.is_matched) / count(*), 2) as unmatched_rate_pct,
    coalesce(sum(r.abs_gap) filter (where not r.is_matched), 0) as abs_gap_brl,
    rank() over (order by count(*) filter (where not r.is_matched) desc) as rank_by_unmatched
from fact_reconciliation r
join dim_product_category c using (category_key)
where r.item_count is not null
group by all
order by unmatched desc, orders desc;

-- name: delivery
select
    count(*) filter (where is_delivered)                                          as delivered_orders,
    count(*) filter (where is_on_time)                                            as on_time_orders,
    count(*) filter (where is_on_time = false)                                    as late_orders,
    round(100.0 * count(*) filter (where is_on_time) / count(*) filter (where is_delivered), 2)          as on_time_rate_pct,
    round(100.0 * count(*) filter (where is_on_time = false) / count(*) filter (where is_delivered), 2)  as late_rate_pct,
    round(median(delivery_days), 1)                                               as median_delivery_days,
    round(avg(review_score) filter (where is_on_time), 3)                         as avg_review_on_time,
    round(avg(review_score) filter (where is_on_time = false), 3)                 as avg_review_late
from fact_orders;

-- name: reviews_by_match
select
    case when is_matched then 'matched' else 'unmatched' end as reconciliation_status,
    count(*)                                   as orders,
    count(review_score)                        as orders_with_review,
    round(avg(review_score), 3)                as avg_review_score,
    round(100.0 * count(*) filter (where review_score <= 2) / count(review_score), 2) as pct_reviews_1_or_2
from fact_orders
where is_matched is not null
group by 1
order by 1;

-- name: reviews_by_category
select
    gap_category,
    count(*)                                   as orders,
    count(review_score)                        as orders_with_review,
    round(avg(review_score), 3)                as avg_review_score
from fact_orders
where gap_category is not null
group by 1
order by orders desc;

-- name: payment_mix
select
    p.payment_type,
    p.description,
    count(*)                                               as orders,
    count(*) filter (where not r.is_matched)               as unmatched,
    round(100.0 * count(*) filter (where not r.is_matched) / count(*), 2) as unmatched_rate_pct,
    coalesce(sum(r.abs_gap) filter (where not r.is_matched), 0) as abs_gap_brl
from fact_reconciliation r
join dim_payment_type p using (payment_type)
group by all
order by orders desc;

-- name: interest_rate_card_share
-- Share of the installment_interest bucket whose paid/sold ratio is one that 3+ orders share.
with ratios as (
    select paid_to_sold_ratio, count(*) over (partition by paid_to_sold_ratio) as n
    from fact_reconciliation where gap_category = 'installment_interest'
)
select
    count(*)                                                     as interest_orders,
    count(*) filter (where n >= 3)                               as on_shared_ratio,
    round(100.0 * count(*) filter (where n >= 3) / count(*), 2)  as on_shared_ratio_pct,
    count(distinct paid_to_sold_ratio) filter (where n >= 3)     as shared_ratios
from ratios;

-- name: discount_split
select
    main_payment_type,
    round(100.0 * -gap / product_value, 0) as discount_pct,
    count(*) as orders
from reconciliation
where gap_category = 'untracked_discount'
group by all
order by main_payment_type, discount_pct;

-- name: missing_items
select
    count(*)                                                        as orders,
    sum(paid_total)                                                 as paid_brl,
    count(*) filter (where order_status in ('canceled', 'unavailable')) as canceled_or_unavailable,
    sum(paid_total) filter (where order_status in ('canceled', 'unavailable')) as canceled_or_unavailable_brl,
    round(100.0 * count(*) filter (where order_status in ('canceled', 'unavailable')) / count(*), 2)
                                                                    as canceled_or_unavailable_pct,
    count(*) filter (where order_status not in ('canceled', 'unavailable')) as open_orders,
    sum(paid_total) filter (where order_status not in ('canceled', 'unavailable')) as open_orders_brl
from reconciliation
where gap_category = 'missing_items';

-- name: sequence_gaps
select
    count(*)                                             as orders_with_sequence_gap,
    count(*) filter (where r.is_matched)                 as still_matched
from reconciliation r
where r.order_id in (select split_part(record_key, '|', 1) from dq_exceptions
                     where check_name = 'payment_sequence_gap');
