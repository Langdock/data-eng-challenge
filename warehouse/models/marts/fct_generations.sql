-- grain: one row per assistant answer (generation), with its usage, cost, and feedback
{{ config(order_by='created_at') }}
select
    -- Explicit aliases: ClickHouse keeps the "g." prefix on names that several join sides share.
    g.message_id as message_id,
    g.conversation_id as conversation_id,
    g.user_id as user_id,
    g.model_id as model_id,
    c.assistant_id,
    c.source,
    g.usage_id,
    g.uncached_input_tokens,
    g.cached_input_tokens,
    g.output_tokens,
    g.cost_usd,
    f.feedback_id,
    f.rating,
    g.created_at as created_at
from {{ ref('int_generations') }} as g
left join {{ ref('stg_conversations') }} as c on g.conversation_id = c.conversation_id
left join {{ ref('stg_feedback') }} as f on g.message_id = f.message_id
