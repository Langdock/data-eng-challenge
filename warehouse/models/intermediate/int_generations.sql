-- grain: one row per assistant answer; usage has no FK, so it joins on the soft key (user_id, model_id, created_at).
select
    m.message_id,
    m.conversation_id,
    -- Explicit aliases: ClickHouse keeps the "m." prefix on names that both join sides share.
    m.user_id as user_id,
    m.model_id as model_id,
    m.created_at as created_at,
    u.usage_id,
    u.uncached_input_tokens,
    u.cached_input_tokens,
    u.output_tokens,
    -- Cached input priced at 0 (no rate in models); Decimal128(10) keeps sub-cent precision.
    (
        u.uncached_input_tokens * toDecimal128(mo.input_cost_per_1k, 10)
        + u.output_tokens * toDecimal128(mo.output_cost_per_1k, 10)
    ) / 1000 as cost_usd
from {{ ref('stg_messages') }} as m
left join {{ ref('stg_usage') }} as u
    on m.user_id = u.user_id and m.model_id = u.model_id and m.created_at = u.created_at
left join {{ ref('stg_models') }} as mo on m.model_id = mo.model_id
where m.type = 'answer'
