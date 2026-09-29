-- Generic check: child row points to a parent that does not exist
-- (for example a payment for an order that is not in the orders table).
select
    '$table'              as table_name,
    c._row_id             as record_id,
    $key_expr_c           as record_key,
    'orphan_foreign_key'  as check_name,
    '$column = ''' || c.$column || ''' not found in $ref_table.$ref_column' as reason,
    '$severity'           as severity
from raw_$table as c
where c.$column is not null
  and not exists (
      select 1 from raw_$ref_table as p where p.$ref_column = c.$column
  )
