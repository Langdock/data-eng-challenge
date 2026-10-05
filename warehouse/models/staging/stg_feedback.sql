-- grain: one row per feedback
select
    toUUID(JSONExtractString(payload, 'id')) as feedback_id,
    toUUID(JSONExtractString(payload, 'message_id')) as message_id,
    toUUID(JSONExtractString(payload, 'user_id')) as user_id,
    toInt8(JSONExtractInt(payload, 'rating')) as rating,
    JSONExtract(payload, 'comment', 'Nullable(String)') as comment,
    parseDateTime64BestEffort(JSONExtractString(payload, 'created_at'), 6, 'UTC') as created_at,
    _loaded_at
from ({{ cdc_current('feedback') }})
