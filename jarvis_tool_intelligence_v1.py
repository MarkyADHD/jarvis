\
from __future__ import annotations

import json
import re
import threading
from typing import Any, Callable, Dict, List, Optional

import requests

VERSION = "1.0.0"
OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
MODEL = "qwen2.5vl:7b"
MAX_STEPS = 6
MAX_STEP_ATTEMPTS = 2

ALLOWED_TOOLS = {
    "web", "open_url", "link", "spotify", "media", "lights",
    "pc", "attachment", "memory",
}

TOOL_DESCRIPTIONS = {
    "web": "Research current/public information. Returns a reply and may return source_url.",
    "open_url": "Open an exact URL, often $last.source_url from a web step.",
    "link": "Open a named Twitch/YouTube/Instagram/X/TikTok/Kick/GitHub profile.",
    "spotify": "Use Jarvis's existing Spotify controls.",
    "media": "Use existing Windows/media controls including volume.",
    "lights": "Use existing room/Nanoleaf/Key Light controls.",
    "pc": "Use existing PC control/Goal Mode. Existing safety remains authoritative.",
    "attachment": "Use an attachment already available to Jarvis.",
    "memory": "Read/use Jarvis memory. Never use for secrets.",
}

COMPOUND_CONNECTORS = (
    " and then ", " then ", " after that ", " afterwards ",
    " followed by ", " and also ",
)

CROSS_TOOL_HINTS = {
    "web": ("find ", "look up", "search ", "research ", "latest ", "official ", "when does", "what date", "price of"),
    "link": (" on twitch", " on youtube", " on instagram", " on tiktok", " on twitter", " on x", " on kick", " on github"),
    "spotify": ("spotify", "play ", "song", "artist", "playlist"),
    "media": ("volume", "mute", "pause", "next track", "previous track"),
    "lights": ("nanoleaf", "key light", "lights", "light ", "brightness"),
    "pc": ("open notepad", "type ", "save ", "on my pc", "on the pc", "open app", "click ", "screen"),
}

HIGH_RISK_PLANNER_PATTERNS = (
    r"\bpasswords?\b", r"\b2fa\b", r"\bverification code\b",
    r"\bprivate key\b", r"\bseed phrase\b",
    r"\bdisable (?:defender|firewall|antivirus|security)\b",
    r"\bformat (?:the )?(?:drive|disk)\b", r"\bdelete everything\b",
)

_LOCK = threading.Lock()


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normal(value: Any) -> str:
    return clean(value).lower()


def _tool_families(goal: str) -> List[str]:
    low = _normal(goal)
    families = []
    for family, hints in CROSS_TOOL_HINTS.items():
        if any(hint in low for hint in hints):
            families.append(family)
    return families


def should_plan(goal: Any) -> bool:
    text = clean(goal)
    low = text.lower()
    if not text:
        return False

    # Never create a new cross-tool path around existing safety controls.
    if any(re.search(p, low, flags=re.I) for p in HIGH_RISK_PLANNER_PATTERNS):
        return False

    families = _tool_families(text)
    if len(set(families)) >= 2:
        return True

    if any(connector in low for connector in COMPOUND_CONNECTORS):
        actions = re.findall(r"\b(open|find|search|research|play|turn|set|show|load|visit|type|save|click|check)\b", low)
        if len(actions) >= 2:
            return True

    if any(x in low for x in ("find ", "search ", "research ", "official ")) and any(
        x in low for x in (
            "open the source", "open the page", "open the announcement",
            "open it", "pull it up", "show me the source",
        )
    ):
        return True

    if low.count(",") >= 1:
        actions = re.findall(r"\b(open|play|turn|set|mute|pause|type|save|find|search)\b", low)
        if len(actions) >= 2:
            return True

    return False


def _extract_json(text: Any) -> Dict[str, Any]:
    raw = clean(text)
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        pass
    a, b = raw.find("{"), raw.rfind("}")
    if a >= 0 and b > a:
        try:
            data = json.loads(raw[a:b+1])
            return data if isinstance(data, dict) else {}
        except Exception:
            pass
    return {}


def _planner_prompt() -> str:
    tool_lines = "\n".join(f"- {name}: {TOOL_DESCRIPTIONS[name]}" for name in sorted(ALLOWED_TOOLS))
    return f"""You are Jarvis Tool Planner.\n\nConvert the user's compound goal into the smallest safe ordered tool plan.\n\nYou may ONLY select these tools:\n{tool_lines}\n\nRULES:\n- Maximum {MAX_STEPS} steps.\n- Never invent shell, PowerShell, cmd, Python, HTTP, filesystem or admin tools.\n- Never bypass confirmations or safety checks in downstream tools.\n- Preserve exact names, handles, URLs, percentages, song titles and quoted text.\n- Do not split one action into pointless micro-steps.\n- For 'find/research X and open the source/announcement', use web then open_url with url='$last.source_url'.\n- For named social profiles, prefer link instead of web.\n- A step may refer to $last.source_url, $last.reply, $step1.source_url, $step2.reply.\n- If the request is really a single ordinary Jarvis action, set use_tool_intelligence=false.\n\nReturn JSON only:\n{{\"use_tool_intelligence\":true,\"goal\":\"short goal\",\"steps\":[{{\"tool\":\"web|open_url|link|spotify|media|lights|pc|attachment|memory\",\"command\":\"natural command\",\"url\":\"\",\"purpose\":\"why\",\"depends_on\":0}}]}}"""


def plan_goal(goal: Any, model_call: Optional[Callable[[str, str], str]] = None) -> Dict[str, Any]:
    goal = clean(goal)
    if not should_plan(goal):
        return {"use_tool_intelligence": False, "goal": goal, "steps": []}

    if model_call is None:
        def model_call(system_prompt: str, user_prompt: str) -> str:
            payload = {
                "model": MODEL,
                "stream": False,
                "format": "json",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "options": {"temperature": 0.05, "num_predict": 900, "num_ctx": 8192},
            }
            response = requests.post(OLLAMA_URL, json=payload, timeout=120)
            response.raise_for_status()
            return str(response.json().get("message", {}).get("content", "") or "")

    data = _extract_json(model_call(_planner_prompt(), goal))
    if not isinstance(data, dict) or not data.get("use_tool_intelligence", True):
        return {"use_tool_intelligence": False, "goal": goal, "steps": []}

    steps = data.get("steps", [])
    if not isinstance(steps, list):
        steps = []

    validated = []
    for raw_index, step in enumerate(steps[:MAX_STEPS], start=1):
        if not isinstance(step, dict):
            continue
        tool = clean(step.get("tool")).lower()
        if tool not in ALLOWED_TOOLS:
            continue
        command = clean(step.get("command"))
        url = clean(step.get("url"))
        if tool == "open_url":
            if not (url or command):
                continue
        elif not command:
            continue
        try:
            depends_on = int(step.get("depends_on") or 0)
        except Exception:
            depends_on = 0
        if depends_on < 0 or depends_on >= raw_index:
            depends_on = 0
        validated.append({
            "index": len(validated) + 1,
            "tool": tool,
            "command": command,
            "url": url,
            "purpose": clean(step.get("purpose")),
            "depends_on": depends_on,
        })

    if not validated:
        return {"use_tool_intelligence": False, "goal": goal, "steps": []}
    return {"use_tool_intelligence": True, "goal": clean(data.get("goal")) or goal, "steps": validated}


def _result_data(result: Any) -> Dict[str, Any]:
    if isinstance(result, dict):
        merged = dict(result.get("data") or {}) if isinstance(result.get("data"), dict) else {}
        for key in ("source_url", "url", "reply", "answer", "status", "mode"):
            if key in result and key not in merged:
                merged[key] = result.get(key)
        return merged
    return {"reply": clean(result)}


def _infer_status(result: Any) -> str:
    if result is None:
        return "failed"
    if isinstance(result, bool):
        return "succeeded" if result else "failed"
    if isinstance(result, dict):
        explicit = clean(result.get("status")).lower()
        if explicit in {"attempted", "succeeded", "failed", "unknown", "blocked"}:
            return explicit
        reply = clean(result.get("reply")).lower()
        if reply and any(x in reply for x in ("couldn't", "could not", "can't ", "cannot ", "failed", "not found", "unable to", "didn't work", "blocked")):
            return "failed"
        if result.get("mode") in {"chat", "action"}:
            return "succeeded"
        return "unknown"
    return "succeeded" if clean(result) else "unknown"


def _resolve_reference(value: Any, outcomes: List[Dict[str, Any]]) -> str:
    text = clean(value)
    if not text.startswith("$"):
        return text
    if text.startswith("$last."):
        if not outcomes:
            return ""
        field = text.split(".", 1)[1]
        return clean((outcomes[-1].get("data") or {}).get(field, ""))
    match = re.fullmatch(r"\$step(\d+)\.([A-Za-z0-9_]+)", text)
    if match:
        target = int(match.group(1))
        field = match.group(2)
        for outcome in outcomes:
            if int(outcome.get("index", 0)) == target:
                return clean((outcome.get("data") or {}).get(field, ""))
    return ""


def _call_handler(handler: Callable[..., Any], step: Dict[str, Any], outcomes: List[Dict[str, Any]]) -> Any:
    if step["tool"] == "open_url":
        url = _resolve_reference(step.get("url") or step.get("command"), outcomes)
        if not url:
            return {"status": "failed", "reply": "No exact URL was available from the previous step."}
        return handler(url)
    command = _resolve_reference(step.get("command"), outcomes) or clean(step.get("command"))
    return handler(command)


def execute_plan(plan: Dict[str, Any], handlers: Dict[str, Callable[..., Any]]) -> Dict[str, Any]:
    outcomes: List[Dict[str, Any]] = []
    for step in plan.get("steps", []) or []:
        tool = step.get("tool")
        handler = handlers.get(tool)
        if handler is None:
            outcomes.append({"index": step.get("index", 0), "tool": tool, "status": "failed", "reply": f"Tool '{tool}' is not available.", "data": {}, "attempts": 0})
            continue

        dependency = int(step.get("depends_on") or 0)
        if dependency:
            dep = next((x for x in outcomes if int(x.get("index", 0)) == dependency), None)
            if dep and dep.get("status") in {"failed", "blocked"}:
                outcomes.append({"index": step.get("index", 0), "tool": tool, "status": "failed", "reply": f"Skipped because step {dependency} did not succeed.", "data": {}, "attempts": 0})
                continue

        final_result = None
        final_status = "unknown"
        attempts = 0
        for attempt in range(1, MAX_STEP_ATTEMPTS + 1):
            attempts = attempt
            try:
                result = _call_handler(handler, step, outcomes)
                status = _infer_status(result)
                final_result, final_status = result, status
                if status in {"succeeded", "attempted", "unknown", "blocked"}:
                    break
            except Exception as e:
                final_result = {"status": "failed", "reply": str(e)}
                final_status = "failed"

        data = _result_data(final_result)
        reply = clean(final_result.get("reply") if isinstance(final_result, dict) else final_result)
        outcomes.append({
            "index": step.get("index", 0), "tool": tool, "status": final_status,
            "reply": reply, "data": data, "attempts": attempts,
            "purpose": step.get("purpose", ""),
        })
        if final_status == "blocked":
            break

    success = (
        len(outcomes) == len(plan.get("steps", []) or []) and
        all(x.get("status") in {"succeeded", "attempted", "unknown"} for x in outcomes)
    )
    return {"goal": plan.get("goal", ""), "success": success, "outcomes": outcomes}


def _best_answer(execution: Dict[str, Any]) -> str:
    outcomes = execution.get("outcomes", []) or []
    for outcome in reversed(outcomes):
        if outcome.get("tool") == "web":
            reply = clean(outcome.get("reply"))
            if reply:
                return reply
    for outcome in reversed(outcomes):
        reply = clean(outcome.get("reply"))
        if reply:
            return reply
    return ""


def final_reply(execution: Dict[str, Any], spoken_name="Sir") -> str:
    outcomes = execution.get("outcomes", []) or []
    best = _best_answer(execution)
    failed = [x for x in outcomes if x.get("status") in {"failed", "blocked"}]
    if not failed:
        if best:
            return f"{best} Done, {spoken_name}." if len(outcomes) > 1 else best
        return f"Done, {spoken_name}."
    if best:
        failed_tools = ", ".join(str(x.get("tool", "step")) for x in failed[:3])
        return f"{best} I couldn't complete {failed_tools}, {spoken_name}."
    reason = clean(failed[0].get("reply")) or "that step failed"
    return f"I couldn't complete the full request, {spoken_name}. {reason}"


def run_goal(goal: Any, handlers: Dict[str, Callable[..., Any]], spoken_name="Sir", model_call: Optional[Callable[[str, str], str]] = None) -> Optional[Dict[str, Any]]:
    if not should_plan(goal):
        return None
    if not _LOCK.acquire(blocking=False):
        return {"mode": "chat", "reply": f"I'm already working through another multi-step task, {spoken_name}.", "steps": [], "_tool_execution": {"success": False, "outcomes": []}}
    try:
        plan = plan_goal(goal, model_call=model_call)
        if not plan.get("use_tool_intelligence"):
            return None
        execution = execute_plan(plan, handlers)
        return {
            "mode": "chat",
            "reply": final_reply(execution, spoken_name=spoken_name),
            "steps": [],
            "_tool_plan": plan,
            "_tool_execution": execution,
        }
    finally:
        _LOCK.release()


def diagnostics(plan: Dict[str, Any], execution: Dict[str, Any]) -> str:
    bits = []
    outcomes = execution.get("outcomes", []) or []
    for step in plan.get("steps", []) or []:
        idx = step.get("index")
        outcome = next((x for x in outcomes if x.get("index") == idx), {})
        bits.append(f"{idx}:{step.get('tool')}={outcome.get('status', 'not-run')}")
    return f"Tool Intelligence V1: steps={len(plan.get('steps', []) or [])}; " + ", ".join(bits)
