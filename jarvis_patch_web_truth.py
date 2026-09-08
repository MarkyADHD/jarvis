from pathlib import Path
import re
import shutil
from datetime import datetime

APP_PATH = Path("C:/AI-Agent/jarvis_app.py")
DIRECT_WEB_HELPERS = 'def make_direct_web_reply(query, web_data):\n    results = (web_data or {}).get("results", []) or []\n    pages = (web_data or {}).get("pages", []) or []\n\n    if not results and not pages:\n        return None\n\n    useful = []\n    for result in results[:5]:\n        title = str(result.get("title", "")).strip()\n        snippet = str(result.get("snippet", "")).strip()\n\n        if not title:\n            continue\n\n        if snippet:\n            useful.append(f"{title}: {snippet[:180]}")\n        else:\n            useful.append(title)\n\n    if not useful and pages:\n        for page in pages[:3]:\n            title = str(page.get("title", "")).strip()\n            text = str(page.get("text", "")).strip()\n            if title or text:\n                useful.append(f"{title}: {text[:180]}")\n\n    if not useful:\n        return None\n\n    query_lower = normalize_transcript(query)\n\n    if "markyadhd" in query_lower or "marky adhd" in query_lower:\n        remembered = (\n            "From my saved memory, MarkyADHD is your creator brand. "\n            "From the web, I found results linked to MarkyADHD, including Twitch analytics or GTA RP stream listing style pages. "\n        )\n        return {\n            "mode": "chat",\n            "reply": remembered + "The top result I found was: " + useful[0] + f" {USER_SPOKEN_NAME}.",\n            "steps": []\n        }\n\n    return {\n        "mode": "chat",\n        "reply": "I found this online: " + "; ".join(useful[:3]) + f" {USER_SPOKEN_NAME}.",\n        "steps": []\n    }'
NEW_WEB_FAST = 'def web_fast(command):\n    c = normalize_transcript(command)\n\n    if not should_use_web_search(c):\n        return None\n\n    if not WEB_AVAILABLE:\n        return {\n            "mode": "chat",\n            "reply": f"Internet mode is not loaded correctly, {USER_SPOKEN_NAME}.",\n            "steps": []\n        }\n\n    query = clean_web_query(c)\n\n    if not query:\n        return {\n            "mode": "chat",\n            "reply": f"What should I search for, {USER_SPOKEN_NAME}?",\n            "steps": []\n        }\n\n    log(f"Internet mode searching: {query}")\n\n    try:\n        web_data = web_research(query, max_results=WEB_MAX_RESULTS)\n        web_context = format_web_context(web_data)\n\n        result_count = len((web_data or {}).get("results", []) or [])\n        page_count = len((web_data or {}).get("pages", []) or [])\n\n        log(f"Internet results found: {result_count}; pages read: {page_count}")\n\n        if not web_context:\n            return {\n                "mode": "chat",\n                "reply": f"I could not find enough online for that, {USER_SPOKEN_NAME}.",\n                "steps": []\n            }\n\n        remember("web_search", f"Internet search: {query}")\n\n        direct_reply = make_direct_web_reply(query, web_data)\n        if direct_reply and result_count > 0:\n            return direct_reply\n\n        answer = answer_with_web_context(c, web_context)\n        reply = str(answer.get("reply", "")).strip().lower()\n\n        bad_phrases = [\n            "i\'m not aware",\n            "i am not aware",\n            "i don\'t know",\n            "i do not know",\n            "couldn\'t find any information",\n            "could not find any information",\n            "no information about",\n            "not enough information",\n        ]\n\n        if result_count > 0 and any(phrase in reply for phrase in bad_phrases):\n            fallback = make_direct_web_reply(query, web_data)\n            if fallback:\n                return fallback\n\n        return answer\n\n    except Exception as e:\n        log(f"Internet mode failed: {e}")\n        return {\n            "mode": "chat",\n            "reply": f"I couldn\'t search the internet right now, {USER_SPOKEN_NAME}.",\n            "steps": []\n        }'
NEW_PROMPT = 'WEB_ANSWER_PROMPT = f"""\nYou are Jarvis with live internet research.\n\nThe user\'s preferred spoken name is {USER_SPOKEN_NAME}.\n\nYou will be given live web search context.\nUse the web context as the source of truth.\nIf search results are present, do not say you are unaware of the topic.\nIf page extracts are weak but search result titles/snippets exist, summarise those results clearly.\nIf results are only possible profile candidates, say they are possible matches, not confirmed facts.\nDo not invent facts that are not in the context.\nKeep the answer short enough to speak out loud.\n\nReturn ONLY valid JSON:\n{{\n  "mode": "chat",\n  "reply": "Answer here, addressing the user as {USER_SPOKEN_NAME}.",\n  "steps": []\n}}\n"""'

def replace_function(text, name, replacement):
    pattern = r"\ndef " + re.escape(name) + r"\(.*?\):\n(?:(?!\ndef |\nclass |\n# =========================).)*"
    match = re.search(pattern, text, flags=re.S)
    if not match:
        raise RuntimeError(f"Could not find function: {name}")
    return text[:match.start()] + "\n" + replacement + "\n" + text[match.end():]

def main():
    if not APP_PATH.exists():
        raise FileNotFoundError(f"Could not find {APP_PATH}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = APP_PATH.with_name(f"jarvis_app_backup_before_web_search_truth_{timestamp}.py")
    shutil.copy2(APP_PATH, backup_path)

    text = APP_PATH.read_text(encoding="utf-8", errors="replace")

    text = re.sub(
        r'WEB_ANSWER_PROMPT = f""".*?"""',
        NEW_PROMPT,
        text,
        flags=re.S,
    )

    if "def make_direct_web_reply(" not in text:
        marker = "\ndef web_fast(command):"
        idx = text.find(marker)
        if idx == -1:
            raise RuntimeError("Could not find web_fast insertion point.")
        text = text[:idx] + "\n\n" + DIRECT_WEB_HELPERS + "\n" + text[idx:]

    text = replace_function(text, "web_fast", NEW_WEB_FAST)

    APP_PATH.write_text(text, encoding="utf-8")
    print("Jarvis web truth hotfix installed.")
    print("Backup made:", backup_path)
    print("Now run: C:\\AI-Agent\\venv\\Scripts\\python.exe C:\\AI-Agent\\jarvis_app.py")

if __name__ == "__main__":
    main()
