-- grain: one row per user (email and name left out: PII not needed for analytics)
select
    user_id,
    department,
    country,
    locale,
    plan,
    created_at
from {{ ref('stg_users') }}
