"""
AI Trading Brain -- the only place an LLM ever gets to influence a
trade decision. Strict boundaries, per the design:

- The model receives ONLY the plain-text context assembled here
  (recent prices, position state, available cash) -- never Trading 212
  credentials, never a generic HTTP/Bash/filesystem tool. Its only
  tool is WebSearch, granted via jarvis_claude_code_v1._run()'s own
  --tools mechanism (the same restricted-capability pattern already
  used elsewhere in this project, e.g. diagnose_project()'s
  tools="Read,Glob,Grep") -- confirmed real and already proven, not
  invented here.
- It must return ONLY a JSON object matching execution/intent.py's
  schema. Malformed, unparseable, or schema-invalid output becomes
  NO_TRADE -- never guessed at, never partially trusted, per the
  design's explicit rule.
- Its output is a PROPOSAL only. It still goes through the exact same
  risk_engine + guardian_financial_gate pipeline as every deterministic
  template strategy -- this module has no more authority than
  strategy_engine.py's SMA crossover.
"""
import json
import re

import jarvis_claude_code_v1 as claude_v1
from jarvis_trader.execution.intent import validate_intent

SYSTEM_PROMPT = """You are a cautious equity research analyst for a small, real-money \
trading account with strict risk limits enforced by separate software \
you do not control. You will be given recent price history and \
account state for one instrument. Research current news and \
sentiment on it using web search, then decide whether to propose a \
trade.

Respond with ONLY a single JSON object, no other text before or \
after it, matching this exact shape:
{
  "action": "NO_TRADE" | "OPEN_POSITION" | "CLOSE_POSITION" | "HOLD",
  "instrument": "<TICKER>_US_EQ",
  "direction": "LONG",
  "position_value": <number, GBP, only when action is OPEN_POSITION>,
  "order_type": "MARKET",
  "confidence": <number between 0.0 and 1.0>,
  "thesis": "<one paragraph explaining your reasoning>",
  "evidence": ["<short bullet>", "..."],
  "risks": ["<short bullet>", "..."]
}

NO_TRADE is a completely valid and often correct answer -- only \
propose a trade when you have a genuine, evidence-based reason to, \
never to create activity. Never propose a short position (direction \
must always be "LONG" -- short selling is permanently disabled on \
this account). Position sizes are small, a few GBP to a few tens of \
GBP -- this is a small real account, not a hedge fund, so do not \
propose large positions."""


def _extract_json(text: str):
    text = (text or "").strip()
    # Models sometimes wrap JSON in a code fence despite instructions --
    # strip it rather than failing closed on a trivial formatting slip.
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    try:
        return json.loads(text)
    except Exception:
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            try:
                return json.loads(brace_match.group(0))
            except Exception:
                return None
        return None


def propose_intent(ticker: str, bars, position_open: bool, cash: float, strategy_id: str = "ai_brain",
                    effort: str = "medium", timeout: int = 120):
    """Returns (TradeIntent, raw_model_output, error_or_None). On ANY
    failure -- model unavailable, malformed JSON, schema-invalid
    output -- returns a NO_TRADE intent. Never guesses, never
    partially trusts model output."""
    recent = bars[-10:] if bars else []
    price_summary = ", ".join(f"{b.timestamp}: {b.close:.2f}" for b in recent)

    prompt = (
        f"Instrument: {ticker}\n"
        f"Recent closes: {price_summary}\n"
        f"Position currently open: {position_open}\n"
        f"Available cash: £{cash:.2f}\n\n"
        "Research this instrument and respond with ONLY the JSON object described in your instructions."
    )

    result = claude_v1._run(
        prompt, system_prompt=SYSTEM_PROMPT, tools="WebSearch",
        effort=effort, timeout=timeout,
    )

    if not result.get("ok"):
        no_trade, _ = validate_intent({"action": "NO_TRADE", "strategy_id": strategy_id})
        return no_trade, result.get("result", ""), f"Model call failed: {result.get('error')}"

    raw_text = result.get("result", "")
    parsed = _extract_json(raw_text)
    if parsed is None:
        no_trade, _ = validate_intent({"action": "NO_TRADE", "strategy_id": strategy_id})
        return no_trade, raw_text, "Model output was not valid JSON -- treated as NO_TRADE."

    parsed["strategy_id"] = strategy_id
    intent, err = validate_intent(parsed)
    if err:
        no_trade, _ = validate_intent({"action": "NO_TRADE", "strategy_id": strategy_id})
        return no_trade, raw_text, f"Model output failed schema validation: {err}"

    return intent, raw_text, None
