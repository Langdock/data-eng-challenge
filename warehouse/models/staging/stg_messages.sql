-- grain: one row per message
select
    toUUID(JSONExtractString(payload, 'id')) as message_id,
    toUUID(JSONExtractString(payload, 'conversation_id')) as conversation_id,
    toUUID(JSONExtractString(payload, 'user_id')) as user_id,
    toUUID(JSONExtractString(payload, 'model_id')) as model_id,
    JSONExtractString(payload, 'role') as role,
    JSONExtractString(payload, 'type') as type,
    JSONExtract(payload, 'content', 'Nullable(String)') as content,
    -- Debezium sends jsonb as a JSON-encoded string.
    JSONExtract(payload, 'tool_payload', 'Nullable(String)') as tool_payload,
    parseDateTime64BestEffort(JSONExtractString(payload, 'created_at'), 6, 'UTC') as created_at,
    _loaded_at
from ({{ cdc_current('messages') }})
