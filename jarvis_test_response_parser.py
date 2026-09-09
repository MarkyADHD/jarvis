"""Regression tests for jarvis_response_v2's model-output parser.

Plain assertions, not a framework -- this module has zero external
dependencies (stdlib json/re only, confirmed), so it runs anywhere with
just a Python interpreter, no pip install needed. That's also why it's
the one test wired into CI (.github/workflows/ci.yml): everything else
in this project needs real hardware/credentials/services (Twitch,
Spotify, smart lights...) that a CI runner doesn't have.
"""
import jarvis_response_v2 as r


def check(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"OK: {label}")


check(
    r.parse_model_plan('<think>I should answer</think>{"mode":"chat","reply":"Hello, Sir.","steps":[]}', name="Sir"),
    {"mode": "chat", "reply": "Hello, Sir.", "steps": []},
    "thinking block + clean JSON",
)

check(
    r.parse_model_plan('```json\n{"answer":"This is fine.","steps":[]}\n```', name="Sir"),
    {"mode": "chat", "reply": "This is fine.", "steps": []},
    "fenced JSON with 'answer' key instead of 'reply'",
)

check(
    r.parse_model_plan("This is just a normal model answer, Sir.", name="Sir"),
    {"mode": "chat", "reply": "This is just a normal model answer, Sir.", "steps": []},
    "plain prose, no JSON at all",
)

# Regression test for a real bug: a local model's JSON answer truncated
# mid-string (num_predict token limit cutting it off) left unbalanced
# braces that relaxed_json_loads could never parse, and the old
# safety-net regex only knew how to strip a bare {"reply": "..."} shape
# -- not the {"mode": "chat", "reply": "...", ...} shape every system
# prompt in this codebase actually asks for. The leading "mode" key
# survived straight into speech, and with TTS dropping punctuation it
# came out sounding like "mode chat reply [answer]". Fixed live; this
# guards against it coming back.
check(
    r.parse_model_plan(
        '{"mode": "chat", "reply": "It is currently 8:15 PM in India, Sir',  # truncated, no closing
        name="Sir",
    ),
    {"mode": "chat", "reply": "It is currently 8:15 PM in India, Sir", "steps": []},
    "truncated JSON with leading mode key (regression: 'mode chat reply' leak)",
)

print("All response parser tests passed.")
