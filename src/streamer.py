"""Continuous live writer: simulates production traffic.

Every STREAM_INTERVAL seconds it inserts a small random batch (1-10) of
new messages into existing conversations, with created_at = now(), so the
database is always growing and analytics can be kept fresh.
"""
import os
import random
import time
import uuid

from psycopg2.extras import Json

from . import db
from . import fakers as fk

INTERVAL = float(os.getenv("STREAM_INTERVAL", "2"))
BATCH_MIN = int(os.getenv("STREAM_BATCH_MIN", "1"))
BATCH_MAX = int(os.getenv("STREAM_BATCH_MAX", "10"))


def log(msg):
    print(f"[streamer] {msg}", flush=True)


def load_refs(conn):
    """Load existing conversations (with a fixed model each) to append to."""
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM models")
        model_ids = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT id, user_id FROM conversations")
        convs = cur.fetchall()
    if not convs or not model_ids:
        raise RuntimeError("no conversations/models found, run the seed first")
    # Assign a stable model per conversation so model_id is consistent.
    conv_model = {cid: random.choice(model_ids) for (cid, _u) in convs}
    log(f"loaded {len(convs)} conversations and {len(model_ids)} models")
    return convs, conv_model


def make_message(convs, conv_model):
    """Return (message_row, kind). user_id and model_id are always populated."""
    conv_id, conv_user_id = random.choice(convs)
    model_id = conv_model[conv_id]
    now = fk.now_utc()
    base = (str(uuid.uuid4()), conv_id, conv_user_id, model_id)
    roll = random.random()
    if roll < 0.45:
        return base + ("user", "prompt", fk.gen_prompt(), None, now), "prompt"
    if roll < 0.60:
        tool = random.choice(fk.TOOLS)
        return base + ("tool", "tool", tool, Json(fk.gen_tool_payload(tool)), now), f"tool:{tool}"
    if roll < 0.70:
        return base + ("assistant", "reasoning", fk.gen_reasoning(), None, now), "reasoning"
    return base + ("assistant", "answer", fk.gen_answer(), None, now), "answer"


MSG_COLS = ["id", "conversation_id", "user_id", "model_id",
            "role", "type", "content", "tool_payload", "created_at"]
USAGE_COLS = ["id", "user_id", "model_id", "uncached_input_tokens",
              "cached_input_tokens", "output_tokens", "created_at"]


def main():
    conn = db.connect()
    conn.autocommit = True
    convs, conv_model = load_refs(conn)
    msg_sql = (f"INSERT INTO messages ({', '.join(MSG_COLS)}) "
               f"VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)")
    usage_sql = (f"INSERT INTO usage ({', '.join(USAGE_COLS)}) "
                 f"VALUES (%s, %s, %s, %s, %s, %s, %s)")
    log(f"streaming every {INTERVAL}s, batch {BATCH_MIN}-{BATCH_MAX}")
    total = 0
    while True:
        n = random.randint(BATCH_MIN, BATCH_MAX)
        kinds = []
        usage_n = 0
        with conn.cursor() as cur:
            for _ in range(n):
                row, kind = make_message(convs, conv_model)
                cur.execute(msg_sql, row)
                kinds.append(kind)
                # Each answer also produces a usage row (token consumption).
                if kind == "answer":
                    uncached, cached, output = fk.gen_usage_tokens()
                    cur.execute(usage_sql, (str(uuid.uuid4()), row[2], row[3],
                                            uncached, cached, output, row[8]))
                    usage_n += 1
        total += n
        log(f"inserted {n} messages ({', '.join(kinds)}), {usage_n} usage, total msgs this run: {total}")
        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
