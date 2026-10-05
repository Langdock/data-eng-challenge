-- grain: one row per message
{{ config(order_by='created_at') }}
select
    m.message_id,
    m.conversation_id,
    m.user_id,
    m.model_id,
    c.assistant_id,
    c.source,
    m.role,
    m.type,
    -- Tool messages carry the tool name in content.
    if(m.type = 'tool', m.content, null) as tool_name,
    m.created_at
from {{ ref('stg_messages') }} as m
left join {{ ref('stg_conversations') }} as c on m.conversation_id = c.conversation_id
