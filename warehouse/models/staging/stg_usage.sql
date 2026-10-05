-- grain: one row per generation (usage record)
select
    toUUID(JSONExtractString(payload, 'id')) as usage_id,
    toUUID(JSONExtractString(payload, 'user_id')) as user_id,
    toUUID(JSONExtractString(payload, 'model_id')) as model_id,
    toInt32(JSONExtractInt(payload, 'uncached_input_tokens')) as uncached_input_tokens,
    toInt32(JSONExtractInt(payload, 'cached_input_tokens')) as cached_input_tokens,
    toInt32(JSONExtractInt(payload, 'output_tokens')) as output_tokens,
    parseDateTime64BestEffort(JSONExtractString(payload, 'created_at'), 6, 'UTC') as created_at,
    _loaded_at
from ({{ cdc_current('usage') }})
