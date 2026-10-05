-- grain: one row per model
select
    model_id,
    name,
    provider,
    input_cost_per_1k,
    output_cost_per_1k
from {{ ref('stg_models') }}
