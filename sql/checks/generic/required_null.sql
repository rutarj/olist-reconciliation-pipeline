-- Generic check: a required (non-nullable) column is empty.
select
    '$table'         as table_name,
    _row_id          as record_id,
    $key_expr        as record_key,
    'required_null'  as check_name,
    '$column is required but empty' as reason,
    '$severity'      as severity
from raw_$table
where $column is null
