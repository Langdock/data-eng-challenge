-- grain: one row per model
select
    toUUID(JSONExtractString(payload, 'id')) as model_id,
    JSONExtractString(payload, 'name') as name,
    JSONExtractString(payload, 'provider') as provider,
    toDecimal64(JSONExtractString(payload, 'input_cost_per_1k'), 5) as input_cost_per_1k,
    toDecimal64(JSONExtractString(payload, 'output_cost_per_1k'), 5) as output_cost_per_1k,
    _loaded_at
from ({{ cdc_current('models') }})
