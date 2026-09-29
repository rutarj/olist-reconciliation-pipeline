-- Business rule: status and delivery date must agree.
select 'orders' as table_name, _row_id as record_id, order_id as record_key,
       'delivered_without_date' as check_name,
       'status is delivered but order_delivered_customer_date is empty' as reason,
       'medium' as severity
from stg_orders
where order_status = 'delivered' and order_delivered_customer_date is null
union all
select 'orders', _row_id, order_id,
       'delivery_date_on_undelivered_order',
       'status is ' || order_status || ' but a customer delivery date exists',
       'medium'
from stg_orders
where order_status <> 'delivered' and order_delivered_customer_date is not null
