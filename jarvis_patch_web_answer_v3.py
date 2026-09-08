
from pathlib import Path
from datetime import datetime
import shutil

P = Path(r"C:\AI-Agent\jarvis_app_v2.py")

if not P.exists():
    raise SystemExit(r"Could not find C:\AI-Agent\jarvis_app_v2.py")

stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
backup = P.with_name(f"jarvis_app_v2_backup_before_web_answer_v3_{stamp}.py")
shutil.copy2(P, backup)

text = P.read_text(encoding="utf-8", errors="replace")

helper = r'''

def grounded_web_answer_v3(goal, web_context):
    name = refresh_spoken_name()

    system_prompt = (
        "You are Jarvis answering from web research that has already been collected. "
        "Use the supplied research as the factual basis. Answer the user's actual question first. "
        "For latest/news requests, lead with the newest important development. "
        "Do not say 'I'm not sure' if the research contains relevant information. "
        "Distinguish confirmed facts from rumours/speculation. Remove duplicate information. "
        "If the research is incomplete, explain what is known and what is missing. "
        "Return JSON only with keys reply and confidence."
    )

    payload = {
        "model": app.OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": f"QUESTION:\n{goal}\n\nWEB RESEARCH:\n{web_context}"
            },
        ],
        "stream": False,
        "format": "json",
        "keep_alive": "30m",
        "options": {
            "temperature": 0.08,
            "num_predict": 750,
            "num_ctx": 8192,
        },
    }

    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json=payload,
            timeout=180,
        )
        response.raise_for_status()
        content = str(response.json().get("message", {}).get("content", "") or "").strip()

        try:
            data = json.loads(content)
        except Exception:
            data = {}

        reply = ""
        if isinstance(data, dict):
            reply = str(
                data.get("reply", "")
                or data.get("answer", "")
                or data.get("summary", "")
                or ""
            ).strip()

        bad = {
            "i'm not sure on that one yet, sir.",
            "im not sure on that one yet, sir.",
            "i'm not sure on that one yet.",
            "im not sure on that one yet.",
        }

        if reply and reply.lower().strip() not in bad:
            return {"mode": "chat", "reply": reply, "steps": []}

    except Exception as e:
        try:
            app.log(f"Grounded web JSON summary failed: {e}")
        except Exception:
            pass

    fallback_payload = {
        "model": app.OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Answer only from the supplied web research. "
                    "Be direct. For latest/news questions, summarize the newest developments first. "
                    "Distinguish confirmed information from rumours. "
                    "Do not say you're not sure when relevant research exists. "
                    "Do not output JSON."
                )
            },
            {
                "role": "user",
                "content": f"QUESTION:\n{goal}\n\nWEB RESEARCH:\n{web_context}"
            },
        ],
        "stream": False,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.1,
            "num_predict": 750,
            "num_ctx": 8192,
        },
    }

    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json=fallback_payload,
            timeout=180,
        )
        response.raise_for_status()
        reply = str(response.json().get("message", {}).get("content", "") or "").strip()
        if reply:
            return {"mode": "chat", "reply": reply, "steps": []}
    except Exception as e:
        try:
            app.log(f"Grounded web plain summary failed: {e}")
        except Exception:
            pass

    return {
        "mode": "chat",
        "reply": f"I found web results for that, {name}, but the local summariser failed to produce a clean answer.",
        "steps": [],
    }

'''

if "def grounded_web_answer_v3(" not in text:
    marker = "\ndef web_fast_v2(command):\n"
    if marker not in text:
        raise SystemExit("Could not find web_fast_v2().")
    text = text.replace(marker, helper + marker, 1)

start = text.find("def web_fast_v2(command):")
end = text.find("\ndef speak_v2(text):", start)

if start < 0 or end < 0:
    raise SystemExit("Could not locate web_fast_v2().")

new_web_fast = r'''def web_fast_v2(command):
    c = app_normalise(command)
    name = refresh_spoken_name()

    if not should_use_web_search_v2(c):
        return None

    if not getattr(app, "WEB_AVAILABLE", False):
        return {
            "mode": "chat",
            "reply": f"Internet mode is not loaded correctly, {name}.",
            "steps": []
        }

    query = clean_web_query_v2(c)

    if not query:
        return {
            "mode": "chat",
            "reply": f"What should I search for, {name}?",
            "steps": []
        }

    try:
        app.log(f"Internet mode searching: {query}")
    except Exception:
        pass

    try:
        web_data = app.web_research(
            query,
            max_results=getattr(app, "WEB_MAX_RESULTS", 8)
        )

        web_context = app.format_web_context(web_data)

        result_count = len((web_data or {}).get("results", []) or [])
        page_count = len((web_data or {}).get("pages", []) or [])

        try:
            app.log(f"Internet results found: {result_count}; pages read: {page_count}")
        except Exception:
            pass

        if not web_context or result_count == 0:
            reply = brain.make_direct_web_summary(c, web_data, name)
            reply = personality.humanise_web_reply(c, reply, name)

            try:
                brain.note_reply(c, reply, was_web=True)
                memory.note_conversation_turn(
                    user_text=c,
                    assistant_text=reply,
                    tags=["web", "no_pages"]
                )
            except Exception:
                pass

            return {"mode": "chat", "reply": reply, "steps": []}

        web_plan = grounded_web_answer_v3(c, web_context)

        try:
            reply = web_plan.get("reply", "")
            brain.note_reply(c, reply, was_web=True)
            memory.note_conversation_turn(
                user_text=c,
                assistant_text=reply,
                tags=["web", "grounded_v3"]
            )
        except Exception:
            pass

        return web_plan

    except Exception as e:
        try:
            app.log(f"Internet mode failed: {e}")
        except Exception:
            pass

        return {
            "mode": "chat",
            "reply": f"I couldn't complete the internet search right now, {name}.",
            "steps": []
        }

'''

text = text[:start] + new_web_fast + text[end:]

P.write_text(text, encoding="utf-8")

verify = P.read_text(encoding="utf-8", errors="replace")

required = [
    "def grounded_web_answer_v3(",
    "web_plan = grounded_web_answer_v3(c, web_context)",
    'tags=["web", "grounded_v3"]',
]

missing = [item for item in required if item not in verify]
if missing:
    raise SystemExit("Verification failed: " + ", ".join(missing))

print("Jarvis Web Answer V3 installed.")
print("Backup:", backup)
print("Verification passed.")
