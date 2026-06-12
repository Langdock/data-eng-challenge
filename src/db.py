"""Postgres connection helpers shared by the seed and streamer."""
import os
import time

import psycopg2


def conn_params():
    return dict(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "postgres"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.getenv("POSTGRES_PASSWORD", "secret"),
    )


def connect(retries=30, delay=2):
    """Connect, retrying while Postgres is still coming up."""
    last = None
    for attempt in range(1, retries + 1):
        try:
            conn = psycopg2.connect(**conn_params())
            conn.autocommit = False
            return conn
        except psycopg2.OperationalError as exc:
            last = exc
            print(f"[db] postgres not ready (attempt {attempt}/{retries}): {exc}", flush=True)
            time.sleep(delay)
    raise last
