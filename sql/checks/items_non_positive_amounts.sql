-- Business rule: an item must have a positive price and a non-negative freight charge.
select 'order_items' as table_name, _row_id as record_id,
       order_id || '|' || order_item_id as record_key,
       'non_positive_price' as check_name,
       'price = ' || price || ' (must be > 0)' as reason,
       'high' as severity
from stg_order_items
where price <= 0
union all
select 'order_items', _row_id, order_id || '|' || order_item_id,
       'negative_freight',
       'freight_value = ' || freight_value || ' (must be >= 0)',
       'high'
from stg_order_items
where freight_value < 0
