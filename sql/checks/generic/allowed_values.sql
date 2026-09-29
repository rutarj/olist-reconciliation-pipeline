-- Generic check: value outside the list of allowed values in the contract.
select
    '$table'          as table_name,
    _row_id           as record_id,
    $key_expr         as record_key,
    'allowed_values'  as check_name,
    '$column = ''' || $column || ''' is not an allowed value' as reason,
    '$severity'       as severity
from raw_$table
where $column is not null
  and try_cast($column as $type) is not null
  and try_cast($column as $type) not in ($allowed_list)
