-- grain: one row per source table. A view, so lag is computed at query time, not at the last dbt run.
with events as (
    select
        tbl,
        _ingested_at,
        -- Nullable so quantiles are NULL, not 0, for tables with no recent events.
        toNullable(toUnixTimestamp64Milli(_ingested_at) - source_ts_ms) as ingest_ms,
        toNullable(ts_ms - source_ts_ms) as capture_ms,
        -- Change events from the last 15 minutes; snapshot rows (op = 'r') would inflate the lags.
        op != 'r' and _ingested_at > now64(3) - interval 15 minute as is_recent
    from {{ source('raw', 'cdc_events') }}
)

select
    tbl as source_table,
    max(_ingested_at) as last_ingested_at,
    dateDiff('second', max(_ingested_at), now64(3)) as staleness_s,
    countIf(is_recent) as events_15m,
    round(quantileIf(0.5) (ingest_ms, is_recent)) as ingest_lag_ms_p50,
    round(quantileIf(0.95) (ingest_ms, is_recent)) as ingest_lag_ms_p95,
    round(quantileIf(0.95) (capture_ms, is_recent)) as capture_lag_ms_p95,
    -- How far the marts trail raw (the dbt loop), independent of whether the source is busy.
    if(
        tbl = 'messages',
        dateDiff(
            'second',
            (select max(f.created_at) from {{ ref('fct_messages') }} as f),
            (select max(s.created_at) from {{ ref('stg_messages') }} as s)
        ),
        null
    ) as mart_lag_s
from events
group by tbl
