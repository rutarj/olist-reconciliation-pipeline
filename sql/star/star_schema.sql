-- Star schema for Power BI (and any BI tool).
-- Facts: fact_orders (1 row per order), fact_reconciliation (1 row per order_id seen in any
-- system), fact_exceptions (1 row per exception). Dimensions join on simple keys.
-- Statements are separated by ';' and run in order by src/star_schema.py.

-- dim_date: one row per calendar day covering every date used by a fact.
create or replace table dim_date as
with bounds as (
    select
        min(order_purchase_timestamp)::date                    as start_date,
        greatest(max(order_estimated_delivery_date)::date,
                 max(order_delivered_customer_date)::date)     as end_date
    from stg_orders
),
days as (
    select unnest(generate_series(start_date, end_date, interval 1 day))::date as d from bounds
)
select
    cast(strftime(d, '%Y%m%d') as integer)  as date_key,
    d                                        as date,
    year(d)                                  as year,
    quarter(d)                               as quarter,
    month(d)                                 as month,
    strftime(d, '%B')                        as month_name,
    strftime(d, '%Y-%m')                     as year_month,
    date_trunc('month', d)::date             as month_start,
    weekofyear(d)                            as iso_week,
    isodow(d)                                as day_of_week,
    strftime(d, '%A')                        as day_name,
    isodow(d) in (6, 7)                      as is_weekend
from days
order by d;

-- dim_customer_state: 27 Brazilian federative units with name and macro-region.
create or replace table dim_customer_state as
select * from (values
    ('AC', 'Acre', 'North'), ('AL', 'Alagoas', 'Northeast'), ('AM', 'Amazonas', 'North'),
    ('AP', 'Amapá', 'North'), ('BA', 'Bahia', 'Northeast'), ('CE', 'Ceará', 'Northeast'),
    ('DF', 'Distrito Federal', 'Center-West'), ('ES', 'Espírito Santo', 'Southeast'),
    ('GO', 'Goiás', 'Center-West'), ('MA', 'Maranhão', 'Northeast'), ('MG', 'Minas Gerais', 'Southeast'),
    ('MS', 'Mato Grosso do Sul', 'Center-West'), ('MT', 'Mato Grosso', 'Center-West'),
    ('PA', 'Pará', 'North'), ('PB', 'Paraíba', 'Northeast'), ('PE', 'Pernambuco', 'Northeast'),
    ('PI', 'Piauí', 'Northeast'), ('PR', 'Paraná', 'South'), ('RJ', 'Rio de Janeiro', 'Southeast'),
    ('RN', 'Rio Grande do Norte', 'Northeast'), ('RO', 'Rondônia', 'North'), ('RR', 'Roraima', 'North'),
    ('RS', 'Rio Grande do Sul', 'South'), ('SC', 'Santa Catarina', 'South'), ('SE', 'Sergipe', 'Northeast'),
    ('SP', 'São Paulo', 'Southeast'), ('TO', 'Tocantins', 'North'),
    ('UNKNOWN', 'Unknown', 'Unknown')
) as t(state_code, state_name, region);

-- dim_payment_type: every payment type seen in the data plus 'none' for orders with no payment.
create or replace table dim_payment_type as
with seen as (
    select distinct payment_type from stg_order_payments where payment_type is not null
    union select 'none'
)
select
    payment_type,
    case payment_type
        when 'credit_card' then 'Credit card (can be split into installments)'
        when 'debit_card'  then 'Debit card'
        when 'boleto'      then 'Boleto bancário (bank slip, paid in cash or online banking)'
        when 'voucher'     then 'Voucher / gift card'
        when 'none'        then 'No payment recorded'
        else 'Not in the contract: ' || payment_type
    end as description,
    payment_type in ('credit_card', 'debit_card') as is_card
from seen
order by payment_type;

-- dim_product_category: Portuguese name -> English name. Untranslated categories keep
-- the Portuguese name; products with no category map to 'unknown'.
create or replace table dim_product_category as
with cats as (
    select distinct coalesce(product_category_name, 'unknown') as category_key from stg_products
    union select 'unknown'
)
select
    c.category_key,
    case when c.category_key = 'unknown' then null else c.category_key end   as category_name_pt,
    coalesce(t.product_category_name_english, c.category_key)                as category_name_en,
    t.product_category_name_english is not null or c.category_key = 'unknown' as has_translation
from cats c
left join (
    select * from stg_category_translation
    qualify row_number() over (partition by product_category_name order by _row_id) = 1
) t on t.product_category_name = c.category_key
order by c.category_key;

-- fact_orders: one row per order in the orders table (first copy if duplicated).
create or replace table fact_orders as
with orders_one as (
    select * from stg_orders
    qualify row_number() over (partition by order_id order by _row_id) = 1
),
main_item as (          -- the most expensive item decides the order's category
    select i.order_id, coalesce(p.product_category_name, 'unknown') as category_key
    from stg_order_items i
    left join (select * from stg_products
               qualify row_number() over (partition by product_id order by _row_id) = 1) p
           using (product_id)
    qualify row_number() over (partition by i.order_id order by i.price desc, i.order_item_id) = 1
),
reviews as (
    select order_id, avg(review_score) as review_score, count(*) as review_count
    from stg_order_reviews group by order_id
)
select
    o.order_id,
    o.customer_id,
    coalesce(c.customer_state, 'UNKNOWN')                                       as state_code,
    cast(strftime(o.order_purchase_timestamp, '%Y%m%d') as integer)             as purchase_date_key,
    cast(strftime(o.order_delivered_customer_date, '%Y%m%d') as integer)        as delivered_date_key,
    cast(strftime(o.order_estimated_delivery_date, '%Y%m%d') as integer)        as estimated_date_key,
    o.order_status,
    coalesce(r.main_payment_type, 'none')                                       as payment_type,
    coalesce(mi.category_key, 'unknown')                                        as category_key,
    o.order_purchase_timestamp,
    o.order_approved_at,
    o.order_delivered_carrier_date,
    o.order_delivered_customer_date,
    o.order_estimated_delivery_date,
    coalesce(r.item_count, 0)                                                   as item_count,
    r.product_value,
    r.freight_value,
    r.expected_total                                                            as sold_value,
    r.paid_total                                                                as paid_value,
    o.order_delivered_customer_date is not null                                 as is_delivered,
    case when o.order_delivered_customer_date is null then null
         else o.order_delivered_customer_date::date <= o.order_estimated_delivery_date::date end as is_on_time,
    date_diff('day', o.order_purchase_timestamp, o.order_delivered_customer_date) as delivery_days,
    rv.review_score,
    coalesce(rv.review_count, 0)                                                as review_count,
    r.is_matched,
    r.gap_category,
    r.has_dq_exception
from orders_one o
left join (select * from stg_customers
           qualify row_number() over (partition by customer_id order by _row_id) = 1) c using (customer_id)
left join reconciliation r using (order_id)
left join main_item mi using (order_id)
left join reviews rv using (order_id);

-- fact_reconciliation: one row per order_id found in ANY system (orders, items, payments).
create or replace table fact_reconciliation as
select
    r.order_id,
    coalesce(r.customer_state, 'UNKNOWN')                                   as state_code,
    cast(strftime(r.order_purchase_timestamp, '%Y%m%d') as integer)         as purchase_date_key,
    coalesce(r.main_payment_type, 'none')                                   as payment_type,
    coalesce(f.category_key, 'unknown')                                     as category_key,
    r.in_orders,
    r.order_status,
    r.item_count,
    r.payment_count,
    r.payment_types,
    r.max_installments,
    r.has_voucher,
    r.product_value,
    r.freight_value,
    r.expected_total,
    r.paid_total,
    r.gap,
    r.abs_gap,
    r.gap_pct,
    r.paid_to_sold_ratio,
    r.is_matched,
    r.gap_category,
    r.severity,
    r.has_dq_exception,
    k.gap_rank_in_month,
    k.gap_rank_in_state,
    k.cumulative_gap_share
from reconciliation r
left join fact_orders f using (order_id)
left join reconciliation_ranked k using (order_id);

-- fact_exceptions: every exception from data quality checks and reconciliation.
create or replace table fact_exceptions as
select
    e.exception_id,
    e.source,
    e.table_name,
    e.record_id,
    e.record_key,
    case when e.table_name in ('orders', 'order_items', 'order_payments', 'reconciliation')
         then split_part(e.record_key, '|', 1) end                          as order_id,
    e.check_name,
    e.reason,
    e.severity,
    f.purchase_date_key,
    f.state_code
from all_exceptions e
left join fact_orders f
       on f.order_id = case when e.table_name in ('orders', 'order_items', 'order_payments', 'reconciliation')
                            then split_part(e.record_key, '|', 1) end;
