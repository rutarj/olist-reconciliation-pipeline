-- Reconciliation step 2: put every order in exactly one bucket.
-- Rules are evaluated top to bottom; the first match wins. The evidence for each rule
-- is produced by sql/reconciliation/04_evidence.sql and written to reports/evidence/.
-- $tolerance is the match tolerance in BRL (0.01).
create or replace table recon_categorized as
select
    r.*,
    case
        when not in_orders                                   then 'orphan_no_order'
        when expected_total is null and paid_total is null   then 'empty_order'
        when paid_total is null                              then 'missing_payment'
        when expected_total is null                          then 'missing_items'
        when abs_gap <= $tolerance                           then 'matched'
        -- each line item is rounded to the cent on its own, so the total can drift by
        -- up to 1 cent per line
        when item_count >= 2 and abs_gap <= 0.01 * item_count then 'rounding'
        -- a voucher is part of the payment; the voucher value and the order total disagree
        when has_voucher                                     then 'voucher_related'
        -- card paid in installments: customer pays interest on top of the item total
        when gap > 0 and only_credit_card and max_installments >= 2 then 'installment_interest'
        -- customer paid exactly 5% or 10% less than the product price: a discount that
        -- was never written into the item price
        when gap < 0 and (
                abs(abs(gap) - round(product_value * 0.05, 2)) <= 0.02
             or abs(abs(gap) - round(product_value * 0.10, 2)) <= 0.02)
                                                             then 'untracked_discount'
        else 'unexplained'
    end as gap_category
from recon_orders r;

create or replace table reconciliation as
select
    c.*,
    case gap_category
        when 'matched'              then null
        when 'rounding'             then 'low'
        when 'installment_interest' then 'low'
        when 'voucher_related'      then 'medium'
        when 'untracked_discount'   then 'medium'
        when 'missing_items'        then case when order_status in ('canceled', 'unavailable')
                                              then 'medium' else 'high' end
        else 'high'   -- missing_payment, orphan_no_order, empty_order, unexplained
    end as severity,
    gap_category = 'matched' as is_matched
from recon_categorized c;
