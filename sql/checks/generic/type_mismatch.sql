-- Generic check: value cannot be converted to the contract type.
-- Raw data is loaded as text, so TRY_CAST returning NULL on a non-empty value means bad data.
select
    '$table'         as table_name,
    _row_id          as record_id,
    $key_expr        as record_key,
    'type_mismatch'  as check_name,
    '$column = ''' || $column || ''' is not a valid $type' as reason,
    '$severity'      as severity
from raw_$table
where $column is not null
  and try_cast($column as $type) is null
