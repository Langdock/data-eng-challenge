"""Fake-but-plausible data generators for the assistant product.

These helpers are shared by the bulk seed and the live streamer so both
produce data with the same shapes and content rules.
"""
import random
import uuid
from datetime import datetime, timedelta, timezone

from faker import Faker

fake = Faker()

DEPARTMENTS = [
    "Engineering", "Sales", "Marketing", "Support", "Finance",
    "People", "Legal", "Product", "Operations", "Research",
]
COUNTRIES = ["US", "DE", "GB", "FR", "ES", "IN", "BR", "JP", "CA", "AU", "NL", "SE"]
LOCALES = ["en-US", "en-GB", "de-DE", "fr-FR", "es-ES", "pt-BR", "ja-JP", "nl-NL"]
PLANS = ["free", "pro", "enterprise"]
PLAN_WEIGHTS = [0.60, 0.30, 0.10]
SOURCES = ["web", "api", "slack", "teams"]
SOURCE_WEIGHTS = [0.55, 0.20, 0.15, 0.10]
TOOLS = ["web_search", "code_interpreter", "image_generation", "create_document", "calendar_lookup"]

# (name, provider, input_cost_per_1k, output_cost_per_1k)
MODELS = [
    ("gpt-4o", "OpenAI", 0.00500, 0.01500),
    ("gpt-4o-mini", "OpenAI", 0.00015, 0.00060),
    ("claude-sonnet-4", "Anthropic", 0.00300, 0.01500),
    ("claude-opus-4", "Anthropic", 0.01500, 0.07500),
    ("gemini-2.0-pro", "Google", 0.00125, 0.00500),
    ("mistral-large", "Mistral", 0.00200, 0.00600),
]

PROMPT_STARTERS = [
    "Can you help me",
    "What's the best way to",
    "Explain how to",
    "Summarize",
    "Draft an email about",
    "Write a short note on",
    "Compare the options for",
    "Walk me through",
    "Give me ideas for",
    "Review this and suggest improvements:",
]

ASSISTANT_NAME_PREFIXES = [
    "Sales", "Support", "Research", "Onboarding", "Finance", "Legal",
    "Marketing", "Recruiting", "Data", "Product", "Engineering", "Travel",
]
ASSISTANT_NAME_SUFFIXES = [
    "Assistant", "Copilot", "Helper", "Bot", "Agent", "Advisor", "Buddy",
]

FEEDBACK_COMMENTS_UP = [
    "Exactly what I needed.", "Great, very clear.", "Super helpful, thanks!",
    "Spot on.", "Saved me a lot of time.", None, None, None,
]
FEEDBACK_COMMENTS_DOWN = [
    "Not quite right.", "Missed the point.", "Too generic.",
    "This is inaccurate.", "Didn't answer my question.", None, None,
]


def now_utc():
    return datetime.now(timezone.utc)


def rand_created(within_days, ref=None):
    """A timestamp uniformly in the last `within_days`, ending ~1h ago."""
    ref = ref or now_utc()
    span = within_days * 24 * 3600
    secs = random.uniform(3600, span)
    return ref - timedelta(seconds=secs)


# --- content generators -----------------------------------------------------

def gen_prompt():
    if random.random() < 0.5:
        return f"{random.choice(PROMPT_STARTERS)} {fake.sentence(nb_words=random.randint(5, 12)).rstrip('.').lower()}?"
    return fake.paragraph(nb_sentences=random.randint(1, 3))


def gen_answer():
    return fake.paragraph(nb_sentences=random.randint(2, 6))


def gen_reasoning():
    return f"To answer this I'll {fake.sentence(nb_words=random.randint(6, 14)).rstrip('.').lower()}."


def gen_text():
    return fake.sentence(nb_words=random.randint(6, 16))


def gen_tool_payload(tool):
    """JSONB payload shaped per tool: {tool, args, input, output}."""
    if tool == "web_search":
        query = fake.sentence(nb_words=5).rstrip(".")
        return {
            "tool": tool,
            "args": {"query": query, "num_results": random.randint(3, 10)},
            "input": {"query": query},
            "output": {
                "results": [
                    {"title": fake.sentence(nb_words=6).rstrip("."),
                     "url": fake.url(),
                     "snippet": fake.sentence()}
                    for _ in range(random.randint(2, 5))
                ]
            },
        }
    if tool == "code_interpreter":
        lang = random.choice(["python", "sql", "bash"])
        return {
            "tool": tool,
            "args": {"language": lang, "timeout_s": random.choice([10, 30, 60])},
            "input": {"code": random.choice([
                "print(sum(range(100)))",
                "SELECT count(*) FROM orders;",
                "df.groupby('country').size()",
            ])},
            "output": {"stdout": str(random.randint(0, 5000)), "exit_code": 0},
        }
    if tool == "image_generation":
        prompt = fake.sentence(nb_words=8).rstrip(".")
        return {
            "tool": tool,
            "args": {"prompt": prompt, "size": random.choice(["512x512", "1024x1024", "1792x1024"]),
                     "style": random.choice(["photo", "illustration", "3d"])},
            "input": {"prompt": prompt},
            "output": {"image_url": fake.image_url(), "seed": random.randint(1, 999_999)},
        }
    if tool == "create_document":
        return {
            "tool": tool,
            "args": {"title": fake.sentence(nb_words=4).rstrip("."),
                     "format": random.choice(["md", "pdf", "docx"])},
            "input": {"sections": random.randint(1, 6)},
            "output": {"document_id": str(uuid.uuid4()), "word_count": random.randint(120, 2400)},
        }
    if tool == "calendar_lookup":
        return {
            "tool": tool,
            "args": {"range": random.choice(["today", "this_week", "next_week"]),
                     "calendar": random.choice(["work", "personal"])},
            "input": {"attendee": fake.email()},
            "output": {
                "events": [
                    {"title": fake.sentence(nb_words=3).rstrip("."), "start": fake.iso8601()}
                    for _ in range(random.randint(0, 4))
                ]
            },
        }
    return {"tool": tool, "args": {}, "input": {}, "output": {}}


def gen_usage_tokens():
    """Plausible (uncached_input, cached_input, output) token counts."""
    uncached = random.randint(50, 4000)
    cached = random.choice([0, 0, 0, random.randint(100, 3000)])  # often no cache hit
    output = random.randint(20, 1500)
    return uncached, cached, output


def gen_assistant_name():
    return f"{random.choice(ASSISTANT_NAME_PREFIXES)} {random.choice(ASSISTANT_NAME_SUFFIXES)}"


def gen_conversation_title():
    return fake.sentence(nb_words=random.randint(3, 7)).rstrip(".")
