CREATE DATABASE IF NOT EXISTS raw;
-- dbt's target; created here so Metabase can connect before the first dbt run.
CREATE DATABASE IF NOT EXISTS analytics;

-- One consumer over all 7 Debezium topics; each message is kept as the raw JSON envelope.
CREATE TABLE IF NOT EXISTS raw.kafka_cdc (message String)
ENGINE = Kafka
SETTINGS
    kafka_broker_list = 'kafka:9092',
    kafka_topic_list = 'pg.public.users,pg.public.models,pg.public.assistants,pg.public.conversations,pg.public.messages,pg.public.usage,pg.public.feedback',
    kafka_group_name = 'ch_raw_v1',
    kafka_format = 'JSONAsString',
    kafka_flush_interval_ms = 1000;

-- Row changes. Replays and snapshot/stream overlap collapse on (tbl, id), latest lsn wins.
CREATE TABLE IF NOT EXISTS raw.cdc_events
(
    tbl          LowCardinality(String),
    op           LowCardinality(String),
    id           String,
    lsn          UInt64,
    source_ts_ms Int64,
    ts_ms        Int64,
    payload      String,
    _ingested_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = ReplacingMergeTree(lsn)
ORDER BY (tbl, id);

CREATE TABLE IF NOT EXISTS raw.cdc_truncates
(
    lsn          UInt64,
    _ingested_at DateTime64(3, 'UTC') DEFAULT now64(3)
)
ENGINE = MergeTree
ORDER BY lsn;

CREATE MATERIALIZED VIEW IF NOT EXISTS raw.mv_cdc_events TO raw.cdc_events AS
SELECT
    splitByChar('.', _topic)[3] AS tbl,
    JSONExtractString(message, 'op') AS op,
    if(JSONHas(message, 'after', 'id'),
       JSONExtractString(message, 'after', 'id'),
       JSONExtractString(message, 'before', 'id')) AS id,
    JSONExtractUInt(message, 'source', 'lsn') AS lsn,
    JSONExtractInt(message, 'source', 'ts_ms') AS source_ts_ms,
    JSONExtractInt(message, 'ts_ms') AS ts_ms,
    JSONExtractRaw(message, 'after') AS payload
FROM raw.kafka_cdc
WHERE JSONExtractString(message, 'op') IN ('r', 'c', 'u', 'd');

CREATE MATERIALIZED VIEW IF NOT EXISTS raw.mv_cdc_truncates TO raw.cdc_truncates AS
SELECT JSONExtractUInt(message, 'source', 'lsn') AS lsn
FROM raw.kafka_cdc
WHERE JSONExtractString(message, 'op') = 't';
