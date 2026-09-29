-- Business rule: order milestones must happen in a sensible order.
-- An order cannot be approved, shipped or delivered before it was purchased (high).
-- Delivered to the customer before the carrier picked it up is almost certainly a
-- data entry error, but the order itself is real (medium).
-- Handed to the carrier before payment approval happens in practice when approval is
-- recorded late, so it is informational only (low).
with o as (
    select
        _row_id,
        order_id,
        order_purchase_timestamp      as purchased,
        order_approved_at             as approved,
        order_delivered_carrier_date  as to_carrier,
        order_delivered_customer_date as delivered
    from stg_orders
),
rules as (
    select _row_id, order_id, 'approved_before_purchase' as check_name, 'high' as severity,
           'approved ' || approved || ' is before purchase ' || purchased as reason
    from o where approved < purchased
    union all
    select _row_id, order_id, 'carrier_before_purchase', 'high',
           'handed to carrier ' || to_carrier || ' before purchase ' || purchased
    from o where to_carrier < purchased
    union all
    select _row_id, order_id, 'delivered_before_purchase', 'high',
           'delivered ' || delivered || ' before purchase ' || purchased
    from o where delivered < purchased
    union all
    select _row_id, order_id, 'delivered_before_carrier', 'medium',
           'delivered ' || delivered || ' before carrier pickup ' || to_carrier
    from o where delivered < to_carrier
    union all
    select _row_id, order_id, 'carrier_before_approval', 'low',
           'handed to carrier ' || to_carrier || ' before approval ' || approved
    from o where to_carrier < approved
)
select 'orders' as table_name, _row_id as record_id, order_id as record_key,
       check_name, reason, severity
from rules
