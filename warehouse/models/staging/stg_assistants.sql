-- grain: one row per assistant
select
    toUUID(JSONExtractString(payload, 'id')) as assistant_id,
    JSONExtractString(payload, 'name') as name,
    JSONExtract(payload, 'description', 'Nullable(String)') as description,
    JSONExtract(payload, 'system_prompt', 'Nullable(String)') as system_prompt,
    toUUIDOrNull(JSONExtractString(payload, 'created_by')) as created_by_user_id,
    parseDateTime64BestEffort(JSONExtractString(payload, 'created_at'), 6, 'UTC') as created_at,
    _loaded_at
from ({{ cdc_current('assistants') }})
