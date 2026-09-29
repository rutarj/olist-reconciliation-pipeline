-- Business rule: payment_sequential should run 1, 2, 3... inside an order.
-- A gap could mean a payment row is missing. LAG() compares each row with the previous one.
-- In this dataset the orders with gaps still reconcile to the cent, which is why this is
-- low severity (see NOTES.md, Decisions).
with seq as (
    select
        _row_id,
        order_id,
        payment_sequential,
        lag(payment_sequential, 1, 0) over (partition by order_id order by payment_sequential) as previous_seq
    from stg_order_payments
)
select 'order_payments' as table_name, _row_id as record_id,
       order_id || '|' || payment_sequential as record_key,
       'payment_sequence_gap' as check_name,
       'payment_sequential jumps from ' || previous_seq || ' to ' || payment_sequential as reason,
       'low' as severity
from seq
where payment_sequential > previous_seq + 1
