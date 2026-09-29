-- Business rule: a review must belong to an order we know about.
select 'order_reviews' as table_name, r._row_id as record_id, r.review_id as record_key,
       'review_unknown_order' as check_name,
       'order_id ' || r.order_id || ' not found in orders' as reason,
       'high' as severity
from stg_order_reviews as r
where r.order_id is not null
  and not exists (select 1 from stg_orders as o where o.order_id = r.order_id)
