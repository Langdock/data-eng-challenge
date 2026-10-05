# Writeup: live Postgres → ClickHouse analytics

## How it works

```
postgres ──WAL (pgoutput)──▶ Debezium (Kafka Connect) ──▶ Kafka: pg.public.<table>
                                                              │
ClickHouse: Kafka engine ─MV─▶ raw.cdc_events  (ReplacingMergeTree(lsn), ORDER BY (tbl, id))
                         └MV─▶ raw.cdc_truncates (one row per TRUNCATE, keyed by LSN)
                                                              │
dbt loop (every 60s): stg_* views → int_generations → dim_* / fct_* tables, freshness view
                                                              │
Metabase: "Product overview" + "Pipeline freshness" dashboards (provisioned by script)
```

`docker compose up --build -d` starts everything; no cloud, no paid services.

## Why this architecture

- **Log-based CDC, not polling.** Seed rows are backdated up to 90 days and ids are UUIDs, so there
  is no reliable `created_at`/id watermark. The WAL gives commit order (LSN) and sees `TRUNCATE`:
  publications publish truncate by default [1], and Debezium emits it as an `op: "t"` event once
  `skipped.operations` is cleared (its default `"t"` drops truncates) [2].
- **Debezium + Kafka** is the boring, well-known pairing. Kafka is not needed for ~3.5 rows/s; it is
  the replay and scaling seam: topics keep everything (`log.retention.ms=-1`), so `raw` can be rebuilt by
  resetting a consumer group to the earliest offset [3], and throughput scales with partitions.
- **ClickHouse** is a laptop-friendly columnar warehouse whose Kafka table engine plus a materialized
  view is the documented way to consume a topic continuously [4], so there is no loader code to own.
- Rejected: a custom `pgoutput` consumer (we would own snapshot/ack correctness; kept as fallback);
  PeerDB (needs a catalog Postgres, Temporal, MinIO, flow workers, and a UI [5]); ClickHouse
  `MaterializedPostgreSQL` (marked experimental, does not replicate DDL [6]); `postgresql()` polling
  (no watermark, blind to TRUNCATE).

**Correctness rules.** Delivery is at-least-once. Duplicates and snapshot/stream overlap collapse in
`ReplacingMergeTree(lsn)`, which keeps the highest version but only at merge time, "at an unknown
time" [7], so staging reads with `FINAL` [7]. `make reseed` truncates all 7 tables in one statement,
under an `ACCESS EXCLUSIVE` lock [8], so one global epoch suffices: staging keeps rows with
`lsn > max(truncate lsn)`. Verified: counts match source after a reseed, a ClickHouse restart, a
Connect restart, and a fresh boot.

## Modelling

| Model | Grain | Answers |
|---|---|---|
| `fct_messages` | message | activity, WAU, channel mix, tool usage |
| `fct_generations` | assistant answer + its usage, `cost_usd`, rating | cost by model/plan/assistant, quality |
| `fct_conversations` | conversation | depth, custom assistant vs plain chat |
| `dim_users` / `dim_assistants` / `dim_models` | one row each | segmentation (email and name dropped: PII) |

Every key is tested `unique` + `not_null`; 41 tests over 15 models in total. Facts are full-rebuilt
tables (~100k rows, seconds).

## Freshness: how it is kept and measured

`analytics.freshness` is a view (computed at query time) over raw CDC metadata, per table:
commit → ClickHouse ingest lag p50/p95, Debezium capture lag, staleness, and how far marts trail raw.
Measured: **ingest p50 ≈ 1s, p95 ≈ 1.5–2s; marts ≤ 60s behind** (the dbt interval). The metric caught a
real event: the laptop slept 31 minutes; after resume it showed a 27-min p95, then recovered with no loss.

## Scaling to 100×

- **Ingest:** the Postgres connector "uses a single task" [2]. Here it snapshotted ~100k rows in
  ~20s (~5k rows/s), far above 100× today's ~3.5 rows/s. Next: Avro + schema registry instead of
  JSON (smaller records, schema evolution [9]), more topic partitions (Debezium keys events by
  primary key [2]), and `kafka_num_consumers` in ClickHouse, up to the partition count [4].
- **Warehouse:** partition `raw` by month [10] and set `do_not_merge_across_partitions_select_final`
  so `FINAL` deduplicates per partition [11]. Make facts incremental (dbt-clickhouse supports it [12]),
  or use ClickHouse refreshable materialized views [13], instead of full rebuilds. Drop pre-truncate
  epochs with a TTL [10] or `ALTER … DELETE`.
- **Ops:** alert on staleness and replication slot lag. An unconsumed slot retains WAL
  indefinitely [14]; cap it with `max_slot_wal_keep_size` (default -1, unlimited [15]), an upstream
  setting I did not change.

## What I would do next

A slot-lag metric (needs a Postgres read). dbt CI on PRs. A configurable cached-token price.
Sessionization (conversation gaps). Retention/cohort marts once the product questions are agreed.

## Assumptions

- **Cached input tokens cost $0**: `models` has no price for them. The token count is kept, so a
  discount rate can be added later.
- **Usage ↔ answer soft join** on (`user_id`, `model_id`, `created_at`), since `usage` has no FK.
  Measured 1:1 (0 usage rows match >1 answer). This is enforced by `unique(usage_id)` in
  `fct_generations` and a warn test for answers older than 5 min with no usage.
- **Static dimensions**: the streamer only inserts `messages` and `usage`, so the other five tables
  only change on reseed. They go through the same CDC path; no special pipelines.
- Foreign-key tests **warn**, not fail: topics land independently, so a child row can briefly
  arrive before its parent (seen during the initial snapshot).
- Timestamps are UTC. Pre-reseed rows stay in `raw` (filtered out by the epoch) as an audit trail.
- Dashboards run on Metabase, whose ClickHouse driver is bundled since Metabase 54 [16].

## Sources

Each link was opened on 2026-10-02 and the cited statement checked.

1. PostgreSQL, CREATE PUBLICATION (`publish` defaults to `insert, update, delete, truncate`): https://www.postgresql.org/docs/current/sql-createpublication.html
2. Debezium PostgreSQL connector (`skipped.operations` default `"t"`; truncate events; single task; key = primary key): https://debezium.io/documentation/reference/stable/connectors/postgresql.html
3. Apache Kafka, basic operations (`--reset-offsets --to-earliest`): https://kafka.apache.org/42/operations/basic-kafka-operations/
4. ClickHouse, Kafka table engine (materialized-view pattern, `kafka_num_consumers`): https://clickhouse.com/docs/engines/table-engines/integrations/kafka
5. PeerDB README (local stack components): https://github.com/PeerDB-io/peerdb
6. ClickHouse, MaterializedPostgreSQL ("This database engine is experimental"): https://clickhouse.com/docs/engines/database-engines/materialized-postgresql
7. ClickHouse, ReplacingMergeTree (deduplication only during merges; `FINAL`): https://clickhouse.com/docs/engines/table-engines/mergetree-family/replacingmergetree
8. PostgreSQL, TRUNCATE (`ACCESS EXCLUSIVE` lock): https://www.postgresql.org/docs/current/sql-truncate.html
9. Debezium, Avro serialization: https://debezium.io/documentation/reference/stable/configuration/avro.html
10. ClickHouse, MergeTree (partition by month; TTL deletes expired rows): https://clickhouse.com/docs/engines/table-engines/mergetree-family/mergetree
11. ClickHouse guide, ReplacingMergeTree (`FINAL` cost; per-partition merges): https://clickhouse.com/docs/guides/replacing-merge-tree
12. ClickHouse, dbt integration (incremental materialization): https://clickhouse.com/docs/integrations/dbt
13. ClickHouse, refreshable materialized views: https://clickhouse.com/docs/materialized-view/refreshable-materialized-view
14. PostgreSQL, logical decoding concepts (slots retain WAL with no consumer): https://www.postgresql.org/docs/current/logicaldecoding-explanation.html
15. PostgreSQL, replication settings (`max_slot_wal_keep_size`): https://www.postgresql.org/docs/current/runtime-config-replication.html
16. ClickHouse/metabase-clickhouse-driver ("promoted … to the core level as of Metabase 54"): https://github.com/ClickHouse/metabase-clickhouse-driver
