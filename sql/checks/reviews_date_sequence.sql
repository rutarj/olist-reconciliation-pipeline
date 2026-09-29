-- Business rule: a review cannot be answered before it was created.
select 'order_reviews' as table_name, _row_id as record_id, review_id as record_key,
       'review_answered_before_created' as check_name,
       'answered ' || review_answer_timestamp || ' before created ' || review_creation_date as reason,
       'medium' as severity
from stg_order_reviews
where review_answer_timestamp < review_creation_date
