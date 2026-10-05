-- The streamer commits an answer and its usage separately, so only answers older than 5 minutes count.
{{ config(severity='warn') }}
select message_id
from {{ ref('fct_generations') }}
where
    usage_id is null
    and created_at < now() - interval 5 minute
