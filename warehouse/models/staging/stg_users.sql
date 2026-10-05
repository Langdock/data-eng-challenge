-- grain: one row per user
select
    toUUID(JSONExtractString(payload, 'id')) as user_id,
    JSONExtractString(payload, 'email') as email,
    JSONExtractString(payload, 'name') as name,
    JSONExtract(payload, 'department', 'Nullable(String)') as department,
    JSONExtract(payload, 'country', 'Nullable(String)') as country,
    JSONExtract(payload, 'locale', 'Nullable(String)') as locale,
    JSONExtractString(payload, 'plan') as plan,
    parseDateTime64BestEffort(JSONExtractString(payload, 'created_at'), 6, 'UTC') as created_at,
    _loaded_at
from ({{ cdc_current('users') }})
