-- grain: one row per conversation
{{ config(order_by='created_at') }}
select
    c.conversation_id,
    c.user_id,
    c.assistant_id,
    c.source,
    c.created_at,
    count(m.message_id) as messages,
    countIf(m.type = 'prompt') as prompts,
    countIf(m.type = 'tool') as tool_calls
from {{ ref('stg_conversations') }} as c
left join {{ ref('stg_messages') }} as m on c.conversation_id = m.conversation_id
group by c.conversation_id, c.user_id, c.assistant_id, c.source, c.created_at
