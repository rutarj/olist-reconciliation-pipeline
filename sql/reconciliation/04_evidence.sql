-- Evidence queries: the data behind each bucket rule. Each query is saved to
-- reports/evidence/<name>.csv. Queries are separated by lines that start with "-- name:".

-- name: rounding_by_item_count
-- Small gaps only happen on multi-item orders and never exceed 1 cent per item.
select
    item_count,
    count(*)                    as orders,
    min(abs_gap)                as min_abs_gap,
    max(abs_gap)                as max_abs_gap
from reconciliation
where abs_gap > 0.01 and abs_gap <= 0.10 and expected_total is not null and paid_total is not null
group by item_count
order by item_count;

-- name: interest_rate_card
-- Overpaid credit card orders: paid/sold ratio clusters on fixed values per installment
-- count. A fixed multiplier shared by many unrelated orders is a pricing rule (card
-- interest), not random error.
select
    max_installments,
    paid_to_sold_ratio,
    count(*) as orders
from reconciliation
where gap_category = 'installment_interest'
group by all
having count(*) >= 3
order by max_installments, orders desc;

-- name: interest_by_installments
-- Median overpayment grows with the number of installments.
select
    max_installments,
    count(*)                         as orders,
    round(median(gap_pct), 2)        as median_gap_pct,
    round(min(gap_pct), 2)           as min_gap_pct,
    round(max(gap_pct), 2)           as max_gap_pct
from reconciliation
where gap_category = 'installment_interest'
group by max_installments
order by max_installments;

-- name: discount_share_of_price
-- Underpaid orders: the missing amount as a share of the product price.
select
    order_id,
    main_payment_type,
    product_value,
    gap,
    round(100.0 * -gap / product_value, 2) as discount_pct_of_price,
    gap_category
from reconciliation
where gap < -0.01 and gap_category in ('untracked_discount', 'unexplained') and expected_total is not null and paid_total is not null
order by discount_pct_of_price;

-- name: missing_items_by_status
-- Orders with a payment but no items: almost all were canceled or unavailable.
select
    order_status,
    count(*)                 as orders,
    sum(paid_total)          as paid_brl
from reconciliation
where gap_category = 'missing_items'
group by order_status
order by orders desc;

-- name: sequence_gap_orders_reconcile
-- Orders whose payment_sequential has holes: do they still reconcile?
select
    r.gap_category,
    count(*) as orders
from reconciliation r
where r.order_id in (
    select split_part(record_key, '|', 1) from dq_exceptions where check_name = 'payment_sequence_gap'
)
group by r.gap_category
order by orders desc;

-- name: voucher_orders
-- Orders paid partly by voucher that do not reconcile.
select order_id, payment_types, expected_total, paid_total, gap, gap_pct
from reconciliation
where gap_category = 'voucher_related'
order by abs_gap desc;
