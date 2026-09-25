"""
Structured trade intent -- the only shape the (future) AI trading
brain will ever be allowed to propose action through. Never free-form
natural language. Malformed, unknown, or ambiguous input is rejected
by validate_intent() -- callers must never execute on anything that
fails validation.

Nothing in this module executes a trade -- it only defines the shape
and validates it. risk/risk_engine.py and risk/guardian_financial_gate
.py decide whether a *validated* intent is actually allowed to
proceed; execution_engine.py (a later phase) would be the only thing
that ever calls the broker to act on one -- it doesn't exist yet.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from jarvis_trader.core.paths import TRADER_ROOT

COUNTER_FILE = TRADER_ROOT / "intent_counter.json"

# Trading 212's own ticker format, confirmed via Phase 1 API research
# (e.g. "AAPL_US_EQ"). A sanity check on shape only -- confirming an
# instrument is real and tradable is a live broker lookup, out of
# scope for a pure schema validator.
_TICKER_RE = re.compile(r"^[A-Z0-9.]{1,12}_[A-Z]{2,6}_EQ$")


class IntentAction(str, Enum):
    NO_TRADE = "NO_TRADE"
    OPEN_POSITION = "OPEN_POSITION"
    REDUCE_POSITION = "REDUCE_POSITION"
    CLOSE_POSITION = "CLOSE_POSITION"
    CANCEL_ORDER = "CANCEL_ORDER"
    HOLD = "HOLD"


class ExecutionState(str, Enum):
    CREATED = "CREATED"
    VALIDATED = "VALIDATED"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    UNCERTAIN = "UNCERTAIN"
    CANCELLED = "CANCELLED"


def next_trade_intent_id() -> str:
    year = datetime.now(timezone.utc).year
    counter = {"year": year, "n": 0}
    if COUNTER_FILE.exists():
        try:
            existing = json.loads(COUNTER_FILE.read_text(encoding="utf-8"))
            if existing.get("year") == year:
                counter = existing
        except Exception:
            pass
    counter["n"] += 1
    counter["year"] = year
    COUNTER_FILE.write_text(json.dumps(counter), encoding="utf-8")
    return f"JT-{year}-{counter['n']:06d}"


@dataclass
class TradeIntent:
    action: str
    instrument: Optional[str] = None
    direction: Optional[str] = None
    strategy_id: Optional[str] = None
    position_value: Optional[float] = None
    order_type: Optional[str] = None
    entry_logic: str = ""
    exit_logic: str = ""
    invalidation: str = ""
    time_horizon: str = ""
    confidence: Optional[float] = None
    thesis: str = ""
    evidence: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    trade_intent_id: str = field(default_factory=next_trade_intent_id)
    execution_state: str = ExecutionState.CREATED.value


def validate_intent(raw: dict):
    """Returns (TradeIntent, None) if valid, or (None, reason) if not.
    Fails closed on anything malformed, unknown, or ambiguous -- per
    the design, DO NOTHING beats guessing what was meant."""
    if not isinstance(raw, dict):
        return None, "Intent was not a JSON object."

    action = raw.get("action")
    if action not in {a.value for a in IntentAction}:
        return None, f"Unknown or missing action: {action!r}."

    if action in (IntentAction.NO_TRADE.value, IntentAction.HOLD.value):
        return TradeIntent(
            action=action,
            strategy_id=raw.get("strategy_id"),
            thesis=str(raw.get("thesis", "")),
        ), None

    instrument = raw.get("instrument")
    if not instrument or not isinstance(instrument, str) or not _TICKER_RE.match(instrument):
        return None, f"Instrument missing or not a recognised Trading 212 ticker format: {instrument!r}."

    if action == IntentAction.OPEN_POSITION.value:
        direction = raw.get("direction")
        if direction != "LONG":
            # SHORT is explicitly and permanently disabled -- see
            # risk/protected_limits.py's SHORT_SELLING_DISABLED.
            return None, f"direction must be 'LONG' (short selling is disabled): {direction!r}."
        position_value = raw.get("position_value")
        if not isinstance(position_value, (int, float)) or isinstance(position_value, bool) or position_value <= 0:
            return None, f"position_value must be a positive number: {position_value!r}."
        order_type = raw.get("order_type")
        if order_type not in ("MARKET", "LIMIT", "STOP", "STOP_LIMIT"):
            return None, f"Unknown order_type: {order_type!r}."
        confidence = raw.get("confidence")
        if confidence is not None and not (isinstance(confidence, (int, float)) and not isinstance(confidence, bool) and 0.0 <= confidence <= 1.0):
            return None, f"confidence must be a number between 0 and 1: {confidence!r}."

    return TradeIntent(
        action=action,
        instrument=instrument,
        direction=raw.get("direction"),
        strategy_id=raw.get("strategy_id"),
        position_value=raw.get("position_value"),
        order_type=raw.get("order_type"),
        entry_logic=str(raw.get("entry_logic", "")),
        exit_logic=str(raw.get("exit_logic", "")),
        invalidation=str(raw.get("invalidation", "")),
        time_horizon=str(raw.get("time_horizon", "")),
        confidence=raw.get("confidence"),
        thesis=str(raw.get("thesis", "")),
        evidence=list(raw.get("evidence") or []),
        risks=list(raw.get("risks") or []),
    ), None
