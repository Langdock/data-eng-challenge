# Data Engineering Take-Home: Live Assistant Analytics

Welcome! This repo gives you a running, **continuously-growing** operational
database for a conversational-AI assistant product. Your job is to ingest it
into an analytical warehouse and build analytics on top. The warehouse side is
**not** included, that's what you'll build.

Scope: roughly **half a day**.

---

## What's provided

A single `docker compose up` starts three things:

1. **`postgres`**: the operational database, with **logical WAL enabled**
   (`wal_level=logical`), so you can use logical replication / CDC if you want.
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

Seed volume and streamer cadence are configurable via env vars, see
`.env.example`.

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

## Deliverables

1. **Code**: your ingestion + warehouse + analytics, runnable with clear
   instructions (ideally `docker compose` or a short script).
2. **A short architecture / trade-offs writeup** (~1 page): how it works, why
   you chose batch vs CDC, how freshness is maintained, what you'd do with more
   time, and any assumptions.

You don't need to modify this repo, treat it as the upstream source system.

---

## Evaluation criteria

- **Correctness**: do the analytics produce right answers against live data?
- **Freshness strategy**: is the incremental/CDC approach sound and justified?
- **Modeling**: is the warehouse schema clean, queryable, and well-reasoned?
- **Code quality**: readable, runnable, sensibly structured.
- **Communication**: clear writeup of decisions and trade-offs.

We care more about **clear thinking and sound trade-offs** than about covering
every nice-to-have. Tell us what you'd do next.

Good luck, have fun with it!
