-- Operational schema for the conversational-AI assistant product.
-- Idempotent: safe to run on every seed startup.

CREATE TABLE IF NOT EXISTS users (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email       text UNIQUE NOT NULL,
    name        text NOT NULL,
    department  text,
    country     text,
    locale      text,
    plan        text NOT NULL CHECK (plan IN ('free', 'pro', 'enterprise')),
    created_at  timestamptz NOT NULL DEFAULT now()
);

-- Reference/lookup table of available models and their pricing.
CREATE TABLE IF NOT EXISTS models (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name               text UNIQUE NOT NULL,
    provider           text NOT NULL,
    input_cost_per_1k  numeric(10, 5) NOT NULL,
    output_cost_per_1k numeric(10, 5) NOT NULL
);

-- Configurable AI agents created by users.
CREATE TABLE IF NOT EXISTS assistants (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name          text NOT NULL,
    description   text,
    system_prompt text,
    created_by    uuid REFERENCES users(id),
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS conversations (
    id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      uuid NOT NULL REFERENCES users(id),
    assistant_id uuid REFERENCES assistants(id),
    title        text,
    source       text NOT NULL CHECK (source IN ('web', 'api', 'slack', 'teams')),
    created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS messages (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id uuid NOT NULL REFERENCES conversations(id),
    user_id         uuid NOT NULL REFERENCES users(id),
    model_id        uuid NOT NULL REFERENCES models(id),
    role            text NOT NULL CHECK (role IN ('user', 'assistant', 'tool')),
    type            text NOT NULL CHECK (type IN ('prompt', 'answer', 'reasoning', 'text', 'tool')),
    content         text,
    tool_payload    jsonb,
    created_at      timestamptz NOT NULL DEFAULT now()
);

-- Per-generation token usage (one row per assistant answer), for cost analytics.
CREATE TABLE IF NOT EXISTS usage (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id               uuid NOT NULL REFERENCES users(id),
    model_id              uuid NOT NULL REFERENCES models(id),
    uncached_input_tokens integer NOT NULL DEFAULT 0,
    cached_input_tokens   integer NOT NULL DEFAULT 0,
    output_tokens         integer NOT NULL DEFAULT 0,
    created_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS feedback (
    id         uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id uuid NOT NULL REFERENCES messages(id),
    user_id    uuid NOT NULL REFERENCES users(id),
    rating     smallint NOT NULL CHECK (rating IN (1, -1)),
    comment    text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_created_at      ON messages (created_at);
CREATE INDEX IF NOT EXISTS idx_messages_conversation_id ON messages (conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_type            ON messages (type);
CREATE INDEX IF NOT EXISTS idx_messages_user_id         ON messages (user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_user_id    ON conversations (user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations (created_at);
CREATE INDEX IF NOT EXISTS idx_feedback_message_id      ON feedback (message_id);
CREATE INDEX IF NOT EXISTS idx_usage_created_at         ON usage (created_at);
CREATE INDEX IF NOT EXISTS idx_usage_user_id            ON usage (user_id);
CREATE INDEX IF NOT EXISTS idx_usage_model_id           ON usage (model_id);
