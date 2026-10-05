# Idempotent Metabase setup: admin user, ClickHouse connection, and the dashboards below (skipped if they exist).
import json
import os
import urllib.request

MB = "http://metabase:3000"
EMAIL = os.environ["MB_ADMIN_EMAIL"]
PASSWORD = os.environ["MB_ADMIN_PASSWORD"]
CH_PASSWORD = os.environ["CLICKHOUSE_PASSWORD"]
DB_NAME = "Warehouse"

# name -> cards as (title, display, sql, visualization_settings, width, height); the grid is 24 wide.
DASHBOARDS = {
    "Product overview": [
        (
            "Weekly active users",
            "line",
            """
            select toStartOfWeek(created_at, 1) as week, uniqExact(user_id) as active_users
            from analytics.fct_messages where type = 'prompt'
            group by week order by week""",
            {},
            12,
            6,
        ),
        (
            "Daily prompts by channel",
            "line",
            """
            select toDate(created_at) as day, source, count() as prompts
            from analytics.fct_messages where type = 'prompt'
            group by day, source order by day""",
            {"graph.dimensions": ["day", "source"], "graph.metrics": ["prompts"]},
            12,
            6,
        ),
        (
            "Weekly cost by model (USD)",
            "bar",
            """
            select toStartOfWeek(g.created_at, 1) as week, m.name as model, round(sum(g.cost_usd), 2) as cost_usd
            from analytics.fct_generations g join analytics.dim_models m using (model_id)
            group by week, model order by week""",
            {
                "graph.dimensions": ["week", "model"],
                "graph.metrics": ["cost_usd"],
                "stackable.stack_type": "stacked",
            },
            12,
            6,
        ),
        (
            "Thumbs-up rate by model (%)",
            "bar",
            """
            select m.name as model, round(avg(g.rating = 1) * 100, 1) as thumbs_up_pct, count() as ratings
            from analytics.fct_generations g join analytics.dim_models m using (model_id)
            where g.rating is not null
            group by model order by thumbs_up_pct desc""",
            {"graph.dimensions": ["model"], "graph.metrics": ["thumbs_up_pct"]},
            12,
            6,
        ),
        (
            "Top assistants (last 30 days)",
            "table",
            """
            select a.name as assistant, uniqExact(g.user_id) as users, count() as answers,
                   round(sum(g.cost_usd), 2) as cost_usd,
                   round(avgIf(g.rating = 1, g.rating is not null) * 100, 1) as thumbs_up_pct
            from analytics.fct_generations g join analytics.dim_assistants a using (assistant_id)
            where g.created_at >= now() - interval 30 day
            group by assistant order by users desc limit 15""",
            {},
            12,
            8,
        ),
        (
            "Cost per active user by plan (last 30 days)",
            "table",
            """
            select u.plan, uniqExact(g.user_id) as active_users, round(sum(g.cost_usd), 2) as cost_usd,
                   round(sum(g.cost_usd) / uniqExact(g.user_id), 2) as cost_per_user,
                   round(sum(g.cached_input_tokens) / sum(g.cached_input_tokens + g.uncached_input_tokens) * 100, 1)
                       as cached_input_pct
            from analytics.fct_generations g join analytics.dim_users u using (user_id)
            where g.created_at >= now() - interval 30 day
            group by u.plan order by cost_per_user desc""",
            {},
            12,
            4,
        ),
        (
            "Custom assistant vs plain chat",
            "table",
            """
            select if(assistant_id is null, 'plain chat', 'custom assistant') as kind,
                   count() as conversations, round(avg(prompts), 1) as avg_prompts,
                   round(avg(tool_calls), 1) as avg_tool_calls
            from analytics.fct_conversations group by kind""",
            {},
            12,
            4,
        ),
        (
            "Tool calls (last 30 days)",
            "row",
            """
            select tool_name, count() as calls from analytics.fct_messages
            where tool_name is not null and created_at >= now() - interval 30 day
            group by tool_name order by calls desc""",
            {},
            24,
            5,
        ),
    ],
    "Pipeline freshness": [
        (
            "Postgres commit → ClickHouse p95 (ms), messages",
            "scalar",
            """
            select ingest_lag_ms_p95 from analytics.freshness where source_table = 'messages'""",
            {},
            8,
            3,
        ),
        (
            "Raw staleness (s), messages",
            "scalar",
            """
            select staleness_s from analytics.freshness where source_table = 'messages'""",
            {},
            8,
            3,
        ),
        (
            "Marts behind raw (s), messages",
            "scalar",
            """
            select mart_lag_s from analytics.freshness where source_table = 'messages'""",
            {},
            8,
            3,
        ),
        (
            "Freshness by source table",
            "table",
            """
            select * from analytics.freshness order by source_table""",
            {},
            24,
            6,
        ),
        (
            "Messages ingested per minute (last hour)",
            "bar",
            """
            select toStartOfMinute(_ingested_at) as minute, count() as events
            from raw.cdc_events where tbl = 'messages' and _ingested_at > now() - interval 1 hour
            group by minute order by minute""",
            {},
            24,
            6,
        ),
    ],
}


def api(method, path, body=None, session=None):
    headers = {"Content-Type": "application/json"}
    if session:
        headers["X-Metabase-Session"] = session
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(
        urllib.request.Request(MB + path, data, headers, method=method)
    ) as r:
        return json.loads(r.read() or "null")


def login():
    props = api("GET", "/api/session/properties")
    if props.get("has-user-setup"):
        return api("POST", "/api/session", {"username": EMAIL, "password": PASSWORD})[
            "id"
        ]
    return api(
        "POST",
        "/api/setup",
        {
            "token": props["setup-token"],
            "user": {
                "email": EMAIL,
                "password": PASSWORD,
                "first_name": "Admin",
                "last_name": "User",
            },
            "prefs": {"site_name": "Assistant Analytics", "allow_tracking": False},
        },
    )["id"]


def database(s):
    for db in api("GET", "/api/database", session=s)["data"]:
        if db["name"] == DB_NAME:
            return db["id"]
    return api(
        "POST",
        "/api/database",
        {
            "engine": "clickhouse",
            "name": DB_NAME,
            "details": {
                "host": "clickhouse",
                "port": 8123,
                "user": "default",
                "password": CH_PASSWORD,
                "dbname": "analytics",
            },
        },
        s,
    )["id"]


def create_dashboard(s, db, name, cards):
    dash = api("POST", "/api/dashboard", {"name": name}, s)
    dashcards, row, col, row_h = [], 0, 0, 0
    for i, (title, display, sql, viz, w, h) in enumerate(cards):
        card = api(
            "POST",
            "/api/card",
            {
                "name": title,
                "display": display,
                "visualization_settings": viz,
                "dataset_query": {
                    "type": "native",
                    "native": {"query": sql.strip()},
                    "database": db,
                },
            },
            s,
        )
        if col + w > 24:
            row, col, row_h = row + row_h, 0, 0
        dashcards.append(
            {
                "id": -(i + 1),
                "card_id": card["id"],
                "row": row,
                "col": col,
                "size_x": w,
                "size_y": h,
            }
        )
        col, row_h = col + w, max(row_h, h)
    api("PUT", f"/api/dashboard/{dash['id']}", {"dashcards": dashcards}, s)
    print(
        f"[metabase-init] created '{name}' ({len(cards)} cards): http://localhost:3000/dashboard/{dash['id']}"
    )


def main():
    s = login()
    db = database(s)
    existing = {d["name"] for d in api("GET", "/api/dashboard", session=s)}
    for name, cards in DASHBOARDS.items():
        if name in existing:
            print(f"[metabase-init] '{name}' exists, skipping")
        else:
            create_dashboard(s, db, name, cards)


if __name__ == "__main__":
    main()
