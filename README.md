# Data Engineering Take-Home: Live Assistant Analytics

Welcome! This repo gives you a running, **continuously-growing** operational
database for a conversational-AI product. Your job is to ingest it
into an analytical warehouse and build analytics on top. The warehouse side is
**not** included, that's what you'll build!

---

## What's provided

A single `docker compose up` starts three things:

1. **`postgres`**: the operational database. It has a wal replication on.
2. **`seed`**: a one-shot container that creates the schema and bulk-loads a
   realistic dataset (~1k users, ~50 assistants, ~5k conversations, ~100k
   messages, plus feedback), then exits. It's idempotent and re-runnable.
3. **`streamer`**: a long-running container that **inserts 1-10 new messages
   into existing conversations every 2 seconds**, simulating live production
   traffic. This is what keeps the database growing while you work.

Data is stored in a named Docker volume (`pgdata`) and persists across restarts
until you reset it.

---

## How to start it

```bash
docker compose up --build
# or, in the background:
make up
```

Within about a minute you'll have a populated database that keeps growing. You
should see the streamer logging inserts:

```
[streamer] inserted 7 messages (prompt, answer, tool:web_search, ...), total this run: 42
```

### Connection details

| Setting  | Value       |
| -------- | ----------- |
| Host     | `localhost` |
| Port     | `5432`      |
| Database | `postgres`  |
| User     | `postgres`  |
| Password | `secret`    |

```bash
psql postgresql://postgres:secret@localhost:5432/postgres
# or:
make psql
```

> These are throwaway dev credentials, there are no secrets in this repo.

### Common commands

| Command       | What it does                                                |
| ------------- | ----------------------------------------------------------- |
| `make up`     | Build + start everything in the background                  |
| `make logs`   | Follow logs from all services                               |
| `make ps`     | Show service status                                         |
| `make psql`   | Open a `psql` shell against the running DB                  |
| `make reseed` | Wipe data and reload the seed in-place (`--force`)          |
| `make down`   | Stop everything **and delete the data volume** (full reset) |

---

## Schema overview

Seven tables. UUID primary keys, `timestamptz` everywhere, real foreign keys,
and indexes on the hot paths (`messages(created_at)`, `messages(conversation_id)`,
`messages(type)`). Full DDL is in [`schema.sql`](./schema.sql).

| Table           | Purpose                                                                                                                                       |
| --------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| `users`         | End users, email, name, department, country, locale, `plan` (free/pro/enterprise)                                                             |
| `models`        | Reference table of models + token pricing (`input/output_cost_per_1k`)                                                                        |
| `assistants`    | Configurable AI agents (name, description, system prompt, `created_by`)                                                                       |
| `conversations` | A thread for a user, optionally tied to an assistant; `source` (web/api/slack/teams)                                                          |
| `messages`      | The fact table, every prompt, answer, reasoning step, tool call                                                                               |
| `feedback`      | Thumbs up/down (`rating` = 1 / -1) on assistant messages, optional comment                                                                    |
| `usage`         | Token usage per generation, `user_id`, `model_id`, `uncached_input_tokens`, `cached_input_tokens`, `output_tokens` (join `models` for $ cost) |

Every `messages` row has a non-null `user_id` (the conversation's user) and
`model_id` (the conversation's model), so you can attribute any message to a
user and model directly.

---

## Your task

**Continuously ingest this live Postgres into an analytical warehouse of your
choice** (ClickHouse, Databricks, Snowflake, Postgres-as-warehouse, …),

The goal is also not just to have the analytical setup but to go down the modelling part as well. Think about what are the interesting dashboards the use cases needs.

---

## Solution: run it and verify it

Every change in Postgres flows, within about a second, into a ClickHouse warehouse; dbt turns it into
analytics tables every minute; Metabase shows the dashboards. Design, trade-offs, and sources:
[`WRITEUP.md`](./WRITEUP.md).

```
Postgres ─WAL─▶ Debezium ─▶ Kafka ─▶ ClickHouse (raw) ─dbt─▶ ClickHouse (analytics) ─▶ Metabase
```

### Prerequisites

- Docker with Docker Compose v2, and about **6 GB of memory** for Docker (Docker Desktop → Settings → Resources).
- Free ports: 5432, 8083, 8123, 3000.
- No `make`? (common on Windows) Each `make` target is one `docker compose` command; see the `Makefile`.

### Run

```bash
make up        # = docker compose up --build -d
```

The first boot takes about 3–4 minutes: images download, the seed loads ~100k messages, and Debezium
copies the existing rows before it starts streaming. After that, the streamer keeps adding data.

| Service | Purpose | Port |
|---|---|---|
| `postgres`, `seed`, `streamer` | Provided source system (unchanged) | 5432 |
| `kafka` | Change-event log (KRaft, single node) | internal 9092 |
| `connect` + `connect-init` | Debezium Postgres connector (WAL / `pgoutput`); `connect-init` registers it once | 8083 |
| `clickhouse` | Warehouse: `raw` (CDC landing) and `analytics` (dbt output) databases | 8123 |
| `dbt` | Runs `dbt build` every `DBT_INTERVAL` s (default 60): 15 models + 41 tests | – |
| `metabase` + `metabase-init` | Dashboards; `metabase-init` creates them once | 3000 |

Settings (passwords, dbt interval, Metabase login) are in [`.env.example`](./.env.example); copy it to
`.env` to override. All credentials are throwaway local defaults.

### Verify it's working

1. **Everything is up:** `docker compose ps`. All services are running/healthy; `seed`,
   `connect-init`, and `metabase-init` show `Exited (0)` (one-shot jobs).
2. **Models and tests pass:** `docker compose logs dbt | grep Done.` → `PASS=56 WARN=0 ERROR=0`.
   The very first build, while the initial copy is still loading, may show a few FK warnings.
3. **Data is fresh:**
   `docker compose exec clickhouse clickhouse-client --password secret -q "SELECT * FROM analytics.freshness"`.
   For `messages`, `staleness_s` stays at a few seconds and `ingest_lag_ms_p95` around 1–2 s.
4. **Dashboards:** http://localhost:3000, log in with `admin@example.com` / `Metabase-admin-1`, open
   *Product overview* and *Pipeline freshness*. Add `#refresh=60` to a dashboard URL to auto-refresh.
5. **Survives a reseed:** `make reseed` (truncates and reloads the source). Within ~2 minutes the
   dashboards recover, with no duplicates.

### Explore the data

| What | How |
|---|---|
| Warehouse SQL shell | `docker compose exec clickhouse clickhouse-client --password secret` |
| Analytics tables | `SHOW TABLES FROM analytics` (`stg_*`, `int_*`, `dim_*`, `fct_*`, `freshness`) |
| Connector status | `curl localhost:8083/connectors/pg/status` |
| Logs of one service | `docker compose logs -f <service>` |

### Stop and reset

`docker compose stop` pauses everything and keeps the data. `make down` (see *Common commands* above)
now deletes Postgres, Kafka, ClickHouse, and Metabase data together, so the next `make up` starts fresh.

To change a dashboard query, edit `dashboards/provision.py`, then
`docker compose rm -sf metabase metabase-init && docker volume rm data-eng-challenge_mbdata && make up`.

### Troubleshooting

- **A service stays unhealthy on first boot:** usually too little memory for Docker; give it ~6 GB and
  run `make up` again (it is safe to re-run).
- **Lag spikes after the laptop sleeps:** expected. Events committed before sleep arrive after
  resume; the freshness numbers return to ~1 s within a minute, with no data lost.

### Development: pre-commit hooks

```bash
pip install pre-commit==4.6.2
pre-commit install --hook-type pre-commit --hook-type commit-msg
pre-commit run --all-files     # optional: check everything once
```

On every commit (config: [`.pre-commit-config.yaml`](./.pre-commit-config.yaml), all versions pinned):

| Check | Catches |
|---|---|
| whitespace, end-of-file, YAML/JSON/TOML/XML syntax, merge markers, large files | Basic hygiene and broken config files |
| `gitleaks` | Committed secrets and private keys |
| `ruff` (lint + format) | Python issues in `dashboards/provision.py` |
| `sqlfluff` ([`.sqlfluff`](./.sqlfluff), ClickHouse dialect) | Style issues in the dbt SQL |
| `docker compose config` | An invalid `docker-compose.yml` (needs Docker running) |
| `dbt parse` | Broken model references or YAML (needs Docker running, ~10–15 s) |
| `conventional-pre-commit` | Commit messages not in the `feat:` / `fix:` / `docs:` style |

The provided upstream code (`src/`, `schema.sql`) is excluded.

### Repository layout

| Path | Contents |
|---|---|
| `ingestion/debezium/` | Debezium connector config |
| `ingestion/clickhouse/` | Raw landing tables (Kafka engine + materialized views) and Kafka client setting |
| `warehouse/` | dbt project (`staging` → `intermediate` → `marts`, `monitoring/freshness`) and its image |
| `dashboards/provision.py` | Metabase setup: admin user, ClickHouse connection, both dashboards |
| `WRITEUP.md` | One-page writeup with sources |

---

### Progress log

1. **Ingestion plan**: Postgres → Debezium → Kafka → ClickHouse → dbt; rejected alternatives are in the writeup.
2. **Ingestion services**: `kafka`, `connect`, `connect-init`, `clickhouse`
   are defined in `docker-compose.yml`. Run: `make up`.
   - **Step 1 verified (CDC capture):** `curl localhost:8083/connectors/pg/status` shows `RUNNING`; all 7
     `pg.public.*` topics carry `r` (snapshot) and `c` (streamed) events; prices arrive as strings, jsonb and
     timestamps as ISO strings; `make reseed` emits `op: "t"` truncate events.
   - **Steps 2–3 verified (landing + reseed):** current rows in ClickHouse
     (`raw.cdc_events FINAL`, after the last truncate) match Postgres on all 7 tables, including after a
     ClickHouse restart, a `make reseed`, and a `connect` restart.
     ClickHouse HTTP: `localhost:8123` (user `default`, password `secret`).
3. **dbt staging layer** (verified: `dbt build` 29/29 green against live data): `warehouse/` holds the dbt project and
   the `dbt` service image, which runs `dbt build` every `DBT_INTERVAL` seconds (default 60).
   Seven `stg_*` views, one per source table, typed from the Debezium JSON. Each keeps only the
   latest version of each row (`FINAL`) written after the last `TRUNCATE`. Every id has `unique` and
   `not_null` tests. Verify: `docker compose logs -f dbt` should show `Completed successfully`.
4. **dbt marts** (verified: `dbt build` 53/53 green): same `dbt` service, no new containers.
   `int_generations` joins each answer to its `usage` row on (user_id, model_id, created_at) and
   prices it (cached input tokens = $0). Marts in the `analytics` database:
   `dim_users`, `dim_assistants`, `dim_models`, `fct_messages` (one row per message),
   `fct_generations` (one row per answer: tokens, `cost_usd`, rating), `fct_conversations`
   (one row per conversation). Grains: see the writeup.
   Verify: `docker compose exec clickhouse clickhouse-client --password secret -q "SELECT count(), sum(cost_usd) FROM analytics.fct_generations"`.
5. **Freshness metric** (verified): view `analytics.freshness`, one row per source table, computed
   at query time: commit → ClickHouse ingest lag (p50/p95, ms), Debezium capture lag (p95, ms),
   raw staleness (s), and how far marts trail raw for `messages` (s). Measured: ≈1–2 s
   Postgres → ClickHouse, ≤60 s to marts.
   Verify: `docker compose exec clickhouse clickhouse-client --password secret -q "SELECT * FROM analytics.freshness"`.
6. **Dashboards** (verified: all 13 cards return data):
   - `metabase` (`metabase/metabase:v0.58.35`, port **3000**): open http://localhost:3000, log in as
     `admin@example.com` / `Metabase-admin-1` (throwaway, overridable in `.env`).
   - `metabase-init` (one-shot, `dashboards/provision.py`): creates the admin user, the ClickHouse
     connection, and two dashboards; skips anything that exists. Log: `docker compose logs metabase-init`.
   - **Product overview**: weekly active users, prompts by channel, weekly cost by model, thumbs-up
     rate by model, top assistants, cost per active user by plan, custom assistant vs plain chat, tool calls.
   - **Pipeline freshness**: ingest p95, raw staleness, marts behind raw, per-table freshness,
     messages ingested per minute. Append `#refresh=60` to the dashboard URL for auto-refresh.
   - After editing card SQL in `provision.py`, re-provision with
     `docker compose rm -sf metabase metabase-init && docker volume rm data-eng-challenge_mbdata && make up`.
7. **Fresh-boot test** (`docker compose down -v` then `up`): found and fixed three startup races
   (missing `analytics` DB for Metabase, Kafka healthcheck timeout under JVM contention, 5-min delay
   before ClickHouse saw late-created topics, fixed by `ingestion/clickhouse/config.d/kafka.xml`).
8. **Writeup**: [`WRITEUP.md`](./WRITEUP.md), with 16 checked sources.
9. **Ponytail review** (−13 lines): dropped config that restated defaults (Debezium port, snapshot mode,
   slot/publication names, table list; ClickHouse user; Kafka rebalance delay; compose `restart: "no"`),
   an unused `.dockerignore`, two unused `fct_conversations` columns, and an unused env override.
   Re-verified with a fresh boot and a `make reseed`: dbt 56/56 green, counts match, all 13 cards return data.
10. **Pre-commit hooks** (14 checks, see *Development* above). The first run reformatted the dbt SQL
    (indentation, `AS` aliases, join order) and `provision.py`; dbt still 56/56 green and all 13 cards
    return data afterwards.

---

## Deliverables

1. **Code**: your ingestion + warehouse + analytics, runnable with clear
   instructions (ideally `docker compose` or a short script) as git repo or zip.
2. **A short writeup** (~1 page): how it works, why
   you chose the architecture, how would you address scaling needs, how freshness is maintained, what you'd do with more
   time, and any assumptions.

---

## Evaluation criteria

Try to invest no more than 6 hours on the challenge. After the challenge please send your submission (fork or zip) in an email to omar.eladawy@langdock.com with karl@langdock.com in CC.

Treat this as not only a platform challenge but a modelling one. What models did you decide for and why, how would you prepare for scaling needs etc. We care more about **clear thinking and sound trade-offs** than about covering every nice-to-have.

Good luck, have fun with it!
