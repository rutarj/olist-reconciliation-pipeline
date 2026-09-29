-- Generic check: duplicate primary key.
-- Flags every copy after the first (the first stays clean), so a key that appears
-- 3 times produces 2 exceptions. Window functions do the counting in one pass.
-- Placeholders (words starting with $$) are filled from config/contracts.yaml by src/validate.py.
with ranked as (
    select
        _row_id,
        $key_expr as record_key,
        row_number() over (partition by $key_cols order by _row_id) as occurrence,
        count(*)     over (partition by $key_cols)                  as copies
    from raw_$table
    where $key_not_null
)
select
    '$table'        as table_name,
    _row_id         as record_id,
    record_key,
    'duplicate_key' as check_name,
    'key ($key_cols) appears ' || copies || ' times; this is copy ' || occurrence as reason,
    '$severity'     as severity
from ranked
where occurrence > 1
