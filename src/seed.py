"""One-shot bulk seed: create schema (idempotent) and load the dataset.

Safe to re-run: if the database is already populated it exits without
changes. Pass --force to truncate everything and reseed from scratch
(used by `make reseed`).
"""
import os
import random
import sys
import uuid
from datetime import timedelta

from psycopg2.extras import Json, execute_values

from . import db
from . import fakers as fk

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "schema.sql")


def env_int(name, default):
    return int(os.getenv(name, default))


CFG = dict(
    users=env_int("SEED_USERS", 1000),
    assistants=env_int("SEED_ASSISTANTS", 50),
    conversations=env_int("SEED_CONVERSATIONS", 5000),
    messages=env_int("SEED_MESSAGES", 100_000),
    days=env_int("SEED_DAYS", 90),
    feedback_rate=float(os.getenv("SEED_FEEDBACK_RATE", "0.15")),
)

ALL_TABLES = ["usage", "feedback", "messages", "conversations", "assistants", "models", "users"]


def log(msg):
    print(f"[seed] {msg}", flush=True)


def apply_schema(conn):
    with open(SCHEMA_PATH) as fh:
        sql = fh.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()
    log("schema applied (idempotent)")


def truncate(conn):
    with conn.cursor() as cur:
        cur.execute(f"TRUNCATE {', '.join(ALL_TABLES)} RESTART IDENTITY CASCADE")
    conn.commit()
    log("truncated all tables")


def already_seeded(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM users")
        return cur.fetchone()[0] > 0


def bulk_insert(conn, table, columns, rows, page_size=1000):
    if not rows:
        return
    sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES %s"
    with conn.cursor() as cur:
        execute_values(cur, sql, rows, page_size=page_size)
    conn.commit()


# --- generation -------------------------------------------------------------

def build_users(n):
    rows = []
    for _ in range(n):
        rows.append((
            str(uuid.uuid4()),
            fk.fake.unique.email(),
            fk.fake.name(),
            random.choice(fk.DEPARTMENTS),
            random.choice(fk.COUNTRIES),
            random.choice(fk.LOCALES),
            random.choices(fk.PLANS, weights=fk.PLAN_WEIGHTS)[0],
            fk.rand_created(CFG["days"]),
        ))
    return rows


def build_models():
    return [
        (str(uuid.uuid4()), name, provider, inc, outc)
        for (name, provider, inc, outc) in fk.MODELS
    ]


def build_assistants(n, user_ids):
    rows = []
    for _ in range(n):
        rows.append((
            str(uuid.uuid4()),
            fk.gen_assistant_name(),
            fk.fake.sentence(nb_words=random.randint(6, 14)),
            f"You are a helpful assistant. {fk.fake.sentence(nb_words=10)}",
            random.choice(user_ids),
            fk.rand_created(CFG["days"]),
        ))
    return rows


def build_conversations(n, user_ids, assistant_ids):
    rows = []
    for _ in range(n):
        rows.append((
            str(uuid.uuid4()),
            random.choice(user_ids),
            random.choice(assistant_ids) if random.random() < 0.7 else None,
            fk.gen_conversation_title(),
            random.choices(fk.SOURCES, weights=fk.SOURCE_WEIGHTS)[0],
            fk.rand_created(CFG["days"]),
        ))
    return rows


def build_messages_for_conversation(conv, model_ids, target_msgs):
    """Build a coherent, time-ordered sequence for one conversation.

    user_id and model_id are always populated: every message belongs to the
    conversation's user and uses the conversation's model.

    Returns (message_rows, answer_records) where answer_records are
    (message_id, user_id, model_id, created_at) tuples — used to derive
    feedback and usage rows.
    """
    conv_id, conv_user_id, _assistant, _title, _source, conv_created = conv
    conv_model = random.choice(model_ids)
    msgs = []
    answers = []
    t = conv_created

    def step():
        nonlocal t
        t = t + timedelta(seconds=random.randint(2, 180))
        return min(t, fk.now_utc())

    def row(role, mtype, content, payload):
        return (str(uuid.uuid4()), conv_id, conv_user_id, conv_model,
                role, mtype, content, payload, step())

    while len(msgs) < target_msgs:
        # user prompt
        msgs.append(row("user", "prompt", fk.gen_prompt(), None))

        # optional assistant reasoning
        if random.random() < 0.4:
            msgs.append(row("assistant", "reasoning", fk.gen_reasoning(), None))

        # optional tool calls
        if random.random() < 0.35:
            for _ in range(random.randint(1, 2)):
                tool = random.choice(fk.TOOLS)
                msgs.append(row("tool", "tool", tool, Json(fk.gen_tool_payload(tool))))

        # occasional plain text chunk
        if random.random() < 0.15:
            msgs.append(row("assistant", "text", fk.gen_text(), None))

        # assistant answer
        ans = row("assistant", "answer", fk.gen_answer(), None)
        msgs.append(ans)
        answers.append((ans[0], conv_user_id, conv_model, ans[8]))

    return msgs, answers


def build_feedback(answers, rate):
    rows = []
    for (msg_id, user_id, _model_id, created) in answers:
        if random.random() >= rate:
            continue
        up = random.random() < 0.78
        rating = 1 if up else -1
        comment = random.choice(fk.FEEDBACK_COMMENTS_UP if up else fk.FEEDBACK_COMMENTS_DOWN)
        fb_created = created + timedelta(seconds=random.randint(10, 7200))
        rows.append((str(uuid.uuid4()), msg_id, user_id, rating, comment,
                     min(fb_created, fk.now_utc())))
    return rows


def build_usage(answers):
    """One usage row per assistant answer (the generation that consumed tokens)."""
    rows = []
    for (_msg_id, user_id, model_id, created) in answers:
        uncached, cached, output = fk.gen_usage_tokens()
        rows.append((str(uuid.uuid4()), user_id, model_id, uncached, cached, output, created))
    return rows


def seed_all(conn):
    log(f"config: {CFG}")

    users = build_users(CFG["users"])
    bulk_insert(conn, "users",
                ["id", "email", "name", "department", "country", "locale", "plan", "created_at"],
                users)
    user_ids = [r[0] for r in users]
    log(f"inserted {len(users)} users")

    models = build_models()
    bulk_insert(conn, "models",
                ["id", "name", "provider", "input_cost_per_1k", "output_cost_per_1k"],
                models)
    model_ids = [r[0] for r in models]
    log(f"inserted {len(models)} models")

    assistants = build_assistants(CFG["assistants"], user_ids)
    bulk_insert(conn, "assistants",
                ["id", "name", "description", "system_prompt", "created_by", "created_at"],
                assistants)
    assistant_ids = [r[0] for r in assistants]
    log(f"inserted {len(assistants)} assistants")

    conversations = build_conversations(CFG["conversations"], user_ids, assistant_ids)
    bulk_insert(conn, "conversations",
                ["id", "user_id", "assistant_id", "title", "source", "created_at"],
                conversations)
    log(f"inserted {len(conversations)} conversations")

    # Messages: aim for ~CFG['messages'] total spread across conversations.
    avg = max(2, CFG["messages"] // max(1, CFG["conversations"]))
    msg_cols = ["id", "conversation_id", "user_id", "model_id",
                "role", "type", "content", "tool_payload", "created_at"]
    total_msgs = 0
    all_answers = []
    batch = []
    for conv in conversations:
        target = max(2, int(random.gauss(avg, avg * 0.4)))
        rows, answers = build_messages_for_conversation(conv, model_ids, target)
        batch.extend(rows)
        all_answers.extend(answers)
        total_msgs += len(rows)
        if len(batch) >= 20_000:
            bulk_insert(conn, "messages", msg_cols, batch)
            log(f"inserted messages: {total_msgs}")
            batch = []
    if batch:
        bulk_insert(conn, "messages", msg_cols, batch)
    log(f"inserted {total_msgs} messages total")

    feedback = build_feedback(all_answers, CFG["feedback_rate"])
    bulk_insert(conn, "feedback",
                ["id", "message_id", "user_id", "rating", "comment", "created_at"],
                feedback)
    log(f"inserted {len(feedback)} feedback rows")

    usage = build_usage(all_answers)
    bulk_insert(conn, "usage",
                ["id", "user_id", "model_id", "uncached_input_tokens",
                 "cached_input_tokens", "output_tokens", "created_at"],
                usage)
    log(f"inserted {len(usage)} usage rows")


def main():
    force = "--force" in sys.argv
    conn = db.connect()
    try:
        apply_schema(conn)
        if force:
            truncate(conn)
        if already_seeded(conn):
            log("database already seeded — nothing to do (use --force to reseed)")
            return
        seed_all(conn)
        log("seed complete")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
