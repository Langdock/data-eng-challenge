-- grain: one row per assistant
select
    assistant_id,
    name,
    description,
    created_by_user_id,
    created_at
from {{ ref('stg_assistants') }}
