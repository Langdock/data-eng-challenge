-- grain: one row per conversation
select
    toUUID(JSONExtractString(payload, 'id')) as conversation_id,
    toUUID(JSONExtractString(payload, 'user_id')) as user_id,
    toUUIDOrNull(JSONExtractString(payload, 'assistant_id')) as assistant_id,
    JSONExtract(payload, 'title', 'Nullable(String)') as title,
    JSONExtractString(payload, 'source') as source,
    parseDateTime64BestEffort(JSONExtractString(payload, 'created_at'), 6, 'UTC') as created_at,
    _loaded_at
from ({{ cdc_current('conversations') }})
