-- Business rule: payment amounts and installment counts must make sense.
-- Negative money is impossible (high). A zero-value payment row adds nothing to the
-- total but is odd (low). Fewer than 1 installment is not a valid plan (medium).
select 'order_payments' as table_name, _row_id as record_id,
       order_id || '|' || payment_sequential as record_key,
       'negative_payment' as check_name,
       'payment_value = ' || payment_value as reason,
       'high' as severity
from stg_order_payments
where payment_value < 0
union all
select 'order_payments', _row_id, order_id || '|' || payment_sequential,
       'zero_value_payment',
       payment_type || ' payment with value 0.00',
       'low'
from stg_order_payments
where payment_value = 0
union all
select 'order_payments', _row_id, order_id || '|' || payment_sequential,
       'invalid_installments',
       payment_type || ' payment with ' || payment_installments || ' installments (must be >= 1)',
       'medium'
from stg_order_payments
where payment_installments < 1
