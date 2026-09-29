-- Reconciliation step 1: one row per order_id with both system totals.
--   System A (sold)  = order_items:     sum(price + freight_value)
--   System B (paid)  = order_payments:  sum(payment_value)
-- The order universe is every order_id seen in ANY of the three tables, so an item or
-- payment with no parent order still shows up (as an orphan) instead of vanishing in a join.
-- Amounts are DECIMAL, not float, so 0.1 + 0.2 really equals 0.3.
create or replace table recon_orders as
with
universe as (
    select order_id from stg_orders         where order_id is not null
    union
    select order_id from stg_order_items    where order_id is not null
    union
    select order_id from stg_order_payments where order_id is not null
),
sold as (                                   -- System A
    select
        order_id,
        count(*)                            as item_count,
        sum(price)                          as product_value,
        sum(freight_value)                  as freight_value,
        sum(price + freight_value)          as expected_total
    from stg_order_items
    group by order_id
),
paid as (                                   -- System B
    select
        order_id,
        count(*)                                        as payment_count,
        sum(payment_value)                              as paid_total,
        max(payment_installments)                       as max_installments,
        bool_or(payment_type = 'voucher')               as has_voucher,
        bool_and(payment_type = 'credit_card')          as only_credit_card,
        string_agg(distinct payment_type, '+' order by payment_type) as payment_types
    from stg_order_payments
    group by order_id
),
first_payment as (                          -- the payment type used to slice KPIs
    select order_id, payment_type as main_payment_type
    from (
        select order_id, payment_type,
               row_number() over (partition by order_id order by payment_value desc, payment_sequential) as rn
        from stg_order_payments
    )
    where rn = 1
),
dq_orders as (                              -- orders touched by any high/medium data quality exception
    select s.order_id from dq_exceptions e join stg_orders s
        on e.table_name = 'orders' and e.record_id = s._row_id
    where e.severity in ('high', 'medium')
    union
    select s.order_id from dq_exceptions e join stg_order_items s
        on e.table_name = 'order_items' and e.record_id = s._row_id
    where e.severity in ('high', 'medium')
    union
    select s.order_id from dq_exceptions e join stg_order_payments s
        on e.table_name = 'order_payments' and e.record_id = s._row_id
    where e.severity in ('high', 'medium')
),
orders_one as (                             -- if an order_id is duplicated, take the first row
    select * from stg_orders
    qualify row_number() over (partition by order_id order by _row_id) = 1
)
select
    u.order_id,
    o.order_id is not null                              as in_orders,
    o.order_status,
    o.order_purchase_timestamp,
    date_trunc('month', o.order_purchase_timestamp)::date as purchase_month,
    c.customer_state,
    s.item_count,
    s.product_value,
    s.freight_value,
    s.expected_total,
    p.payment_count,
    p.paid_total,
    p.payment_types,
    fp.main_payment_type,
    p.max_installments,
    coalesce(p.has_voucher, false)                      as has_voucher,
    coalesce(p.only_credit_card, false)                 as only_credit_card,
    coalesce(p.paid_total, 0) - coalesce(s.expected_total, 0)            as gap,
    abs(coalesce(p.paid_total, 0) - coalesce(s.expected_total, 0))       as abs_gap,
    round(100.0 * (p.paid_total - s.expected_total) / nullif(s.expected_total, 0), 4) as gap_pct,
    round(p.paid_total / nullif(s.expected_total, 0), 4)                  as paid_to_sold_ratio,
    d.order_id is not null                              as has_dq_exception
from universe u
left join orders_one o      using (order_id)
left join stg_customers c   on c.customer_id = o.customer_id
left join sold s            using (order_id)
left join paid p            using (order_id)
left join first_payment fp  using (order_id)
left join (select distinct order_id from dq_orders) d using (order_id);
