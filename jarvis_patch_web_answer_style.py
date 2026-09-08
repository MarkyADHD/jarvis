from pathlib import Path
from datetime import datetime
import re
import sys

APP_PATH = Path(r"C:\AI-Agent\jarvis_app.py")

NEW_WEB_PROMPT = r'''WEB_ANSWER_PROMPT = f"""
You are Jarvis with live internet access.

The user's preferred spoken name is {USER_SPOKEN_NAME}.

You will be given live web search context and sometimes local memory.
Your job is NOT to read out search results.
Your job is to answer the user's exact question directly.

Core behaviour:
- Answer the question first, naturally.
- Use search results as background evidence, not as the final answer format.
- Do not list every result unless the user asks for links or asks what you found.
- Do not say "I found result 1, result 2" as the main answer.
- Do not say "I am not aware" if the web context or local memory contains relevant information.
- If public information is limited, say the answer with a confidence caveat.
- Do not include raw URLs unless the user asks for links.
- Keep it short enough to speak out loud.
- Address the user as {USER_SPOKEN_NAME} once.

Question styles:
- If the user asks "who is X", explain who/what X appears to be, what they are known for, and where the information points.
- If the user asks "what is X", explain it clearly in plain English.
- If the user asks for latest/current/today/news, prioritise recent dated information in the web context.
- If the user asks for a price, say the approximate price/range and mention if it varies.
- If the user says "tell me more", continue the previous topic and add useful detail, not random small talk.

Return ONLY valid JSON:
{{
  "mode": "chat",
  "reply": "Direct answer here.",
  "steps": []
}}
"""'''

NEW_FUNCTIONS = r'''def classify_web_question(goal):
    c = normalize_transcript(goal)

    if re.search(r"\b(who is|who are|who's|whos)\b", c):
        return "identity"

    if re.search(r"\b(what is|what are|what's|whats)\b", c):
        return "definition"

    if any(word in c for word in ["latest", "current", "today", "news", "update", "announced", "released", "release date"]):
        return "current"

    if any(word in c for word in ["price", "cost", "worth", "value", "cheapest", "deal", "buy"]):
        return "price"

    if c in ["tell me more", "go on", "more", "explain more"] or c.startswith("tell me more"):
        return "followup"

    return "general"


def extract_web_titles_from_context(web_context, limit=4):
    titles = []

    for line in str(web_context).splitlines():
        line = line.strip()
        match = re.match(r"^\d+\.\s+(.+)$", line)

        if match:
            title = match.group(1).strip()

            if title and not title.lower().startswith("url:"):
                titles.append(title)

        if len(titles) >= limit:
            break

    return titles


def extract_topic_from_web_question(goal):
    c = normalize_transcript(goal)

    patterns = [
        r"who is\s+(.+)",
        r"who are\s+(.+)",
        r"what is\s+(.+)",
        r"what are\s+(.+)",
        r"tell me about\s+(.+)",
        r"search the internet for\s+(.+)",
        r"search online for\s+(.+)",
        r"look up\s+(.+)",
        r"research\s+(.+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, c)
        if match:
            topic = match.group(1).strip()
            return topic[:80]

    return c[:80]


def web_context_has_results(web_context):
    text = str(web_context).lower()
    return "search results:" in text or "readable page extracts:" in text


def repair_weak_web_answer(goal, plan, web_context):
    if not isinstance(plan, dict):
        return plan

    reply = str(plan.get("reply", "")).strip()
    lowered = reply.lower()

    weak_phrases = [
        "i'm not aware",
        "i am not aware",
        "i couldn't find any information",
        "i could not find any information",
        "i don't know anything",
        "i do not know anything",
        "no information about",
        "can you please provide more context",
        "please provide more context",
    ]

    if not any(phrase in lowered for phrase in weak_phrases):
        return plan

    if not web_context_has_results(web_context):
        return plan

    topic = extract_topic_from_web_question(goal)
    context_lower = str(web_context).lower()

    identity_bits = []

    if any(word in context_lower for word in ["twitch", "stream", "streamer", "streams"]):
        identity_bits.append("a gaming content creator or streamer")

    if any(word in context_lower for word in ["youtube", "tiktok", "instagram", "kick", "x.com", "twitter"]):
        identity_bits.append("with social or creator-platform links")

    if any(word in context_lower for word in ["gta", "gta rp", "roleplay", "hasroot", "nopixel"]):
        identity_bits.append("connected to GTA or GTA RP content")

    if any(word in context_lower for word in ["streamscharts", "stats", "analytics", "viewer"]):
        identity_bits.append("with public stream-stat/profile pages online")

    if identity_bits:
        description = ", ".join(identity_bits[:3])
        answer = f"{topic} appears to be {description}. Public information looks fairly limited, so I’d treat that as a profile-level answer rather than a full biography, {USER_SPOKEN_NAME}."
    else:
        titles = extract_web_titles_from_context(web_context, limit=2)
        if titles:
            answer = f"{topic} does have some public web mentions, but the information looks limited. Based on the results, it appears to be connected to {titles[0]}, {USER_SPOKEN_NAME}."
        else:
            answer = f"{topic} has some public web mentions, but there is not enough reliable detail for a full answer, {USER_SPOKEN_NAME}."

    fixed = dict(plan)
    fixed["mode"] = "chat"
    fixed["reply"] = answer
    fixed["steps"] = []
    log("Repaired weak web answer using search context.")
    return fixed


def answer_with_web_context(goal, web_context):
    answer_style = classify_web_question(goal)
    memory_context = format_memory_context(goal)

    style_instructions = {
        "identity": "The user is asking who someone or something is. Give a direct identity-style answer. Do not list results. Say what they appear to be known for and mention uncertainty if public info is limited.",
        "definition": "The user is asking what something is. Give a direct plain-English explanation. Do not list results.",
        "current": "The user wants current/latest information. Prioritise recent dated information in the context. Summarise the actual update, not every result.",
        "price": "The user wants a price/value/deal style answer. Give a useful range or summary, and mention that prices vary if needed.",
        "followup": "The user is asking for more detail about the previous topic. Continue the topic directly and add useful detail.",
        "general": "Answer the user's question directly using the context. Do not read out search results.",
    }

    messages = [
        {"role": "system", "content": WEB_ANSWER_PROMPT},
        {"role": "system", "content": "Answer style: " + answer_style + "\n" + style_instructions.get(answer_style, style_instructions["general"])},
    ]

    if memory_context:
        messages.append({
            "role": "system",
            "content": "Local memory that may help personalise or clarify the answer:\n" + memory_context
        })

    messages.extend([
        {"role": "system", "content": "Live web context. Use this as background evidence, not as a list to read aloud:\n" + str(web_context)},
        {"role": "user", "content": "User question: " + str(goal) + "\n\nGive the final spoken answer only inside JSON. Do not list search results unless asked."},
    ])

    response = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": False,
            "format": "json",
            "keep_alive": "30m",
            "options": {
                "temperature": 0.1,
                "num_predict": 280,
                "num_ctx": 8192
            }
        },
        timeout=180
    )

    response.raise_for_status()
    content = response.json()["message"]["content"]

    try:
        plan = json.loads(content)
        return repair_weak_web_answer(goal, plan, web_context)

    except json.JSONDecodeError:
        fallback = {
            "mode": "chat",
            "reply": f"I searched, but the model gave me a messy answer, {USER_SPOKEN_NAME}.",
            "steps": []
        }
        return repair_weak_web_answer(goal, fallback, web_context)
'''


def replace_web_prompt(text):
    marker = 'WEB_ANSWER_PROMPT = f"""'
    start = text.find(marker)
    if start == -1:
        raise RuntimeError("Could not find WEB_ANSWER_PROMPT in jarvis_app.py")

    pos = start + len(marker)
    end = text.find('"""', pos)
    if end == -1:
        raise RuntimeError("Could not find end of WEB_ANSWER_PROMPT block")

    end += 3
    return text[:start] + NEW_WEB_PROMPT + text[end:]


def replace_answer_function(text):
    start = text.find('def answer_with_web_context(goal, web_context):')
    if start == -1:
        raise RuntimeError("Could not find answer_with_web_context function")

    next_markers = [
        '\n\ndef web_fast(command):',
        '\n# =========================\n# FULL SKILL MODE',
    ]

    ends = []
    for marker in next_markers:
        pos = text.find(marker, start)
        if pos != -1:
            ends.append(pos)

    if not ends:
        raise RuntimeError("Could not find where answer_with_web_context function ends")

    end = min(ends)

    # Remove older helper functions from a previous run if they were inserted immediately before answer_with_web_context.
    helper_start = text.rfind('\ndef classify_web_question(goal):', 0, start)
    if helper_start != -1:
        section_after_helper = text.find('def answer_with_web_context(goal, web_context):', helper_start)
        if section_after_helper == start:
            start = helper_start + 1

    return text[:start] + NEW_FUNCTIONS + text[end:]


def main():
    if not APP_PATH.exists():
        print(f"Could not find {APP_PATH}")
        sys.exit(1)

    text = APP_PATH.read_text(encoding="utf-8", errors="replace")

    backup = APP_PATH.with_name(f"jarvis_app_backup_before_answer_style_{datetime.now().strftime('%Y%m%d_%H%M%S')}.py")
    backup.write_text(text, encoding="utf-8")

    text = replace_web_prompt(text)
    text = replace_answer_function(text)

    APP_PATH.write_text(text, encoding="utf-8")

    print("Patched Jarvis web answer style successfully.")
    print(f"Backup saved to: {backup}")
    print("Now run: cd C:\\AI-Agent && .\\venv\\Scripts\\python.exe .\\jarvis_app.py")


if __name__ == "__main__":
    main()
