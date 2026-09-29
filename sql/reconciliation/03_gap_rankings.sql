-- Reconciliation step 3: window functions to find where the money is.
--   gap_rank_in_month   1 = biggest gap in that purchase month
--   gap_rank_in_state   1 = biggest gap in that customer state
--   cumulative_gap_share running share of all unmatched money, biggest gaps first (Pareto)
create or replace table reconciliation_ranked as
with unmatched as (
    select * from reconciliation where not is_matched
)
select
    order_id,
    purchase_month,
    customer_state,
    gap_category,
    severity,
    gap,
    abs_gap,
    dense_rank() over (partition by purchase_month order by abs_gap desc) as gap_rank_in_month,
    dense_rank() over (partition by customer_state order by abs_gap desc) as gap_rank_in_state,
    round(sum(abs_gap) over (order by abs_gap desc, order_id
                             rows between unbounded preceding and current row)
          / sum(abs_gap) over (), 6)                                       as cumulative_gap_share,
    row_number() over (order by abs_gap desc, order_id)                    as overall_rank
from unmatched;

-- Month-level view: gap per month and change vs the previous month (LAG).
create or replace table reconciliation_monthly as
with m as (
    select
        purchase_month,
        count(*)                                        as orders,
        count(*) filter (where is_matched)              as matched_orders,
        count(*) filter (where not is_matched)          as unmatched_orders,
        sum(abs_gap) filter (where not is_matched)      as abs_gap_brl
    from reconciliation
    where purchase_month is not null
    group by purchase_month
)
select
    *,
    round(100.0 * matched_orders / orders, 4)                           as match_rate_pct,
    unmatched_orders - lag(unmatched_orders) over (order by purchase_month) as unmatched_change_vs_prev_month
from m
order by purchase_month;
