FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.12.22 /uv /bin/uv

WORKDIR /dbt
COPY pyproject.toml .
RUN uv pip install --system --no-cache -r pyproject.toml

COPY . .

ENV DBT_PROFILES_DIR=/dbt
# A failed build (e.g. a test during reseed) must not kill the loop; the next run retries.
CMD ["sh", "-c", "while true; do dbt build || true; sleep \"${DBT_INTERVAL:-60}\"; done"]
