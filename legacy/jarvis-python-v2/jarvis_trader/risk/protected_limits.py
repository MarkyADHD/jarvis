"""
Protected risk envelope -- the deterministic boundaries JarvisTrader's
AI brain operates inside and cannot see, propose changing, or reach
through any normal code-editing flow.

THESE VALUES ARE OWNER-ONLY. Per the design agreed with the user:
Jarvis, JarvisCode, an AI-generated strategy, and a natural-language
instruction ("Jarvis increase your trading limit") must NEVER change
this file. Guardian's own AST-sandbox protection is currently disabled
project-wide (see jarvis_guardian_v1.py's docstring), so nothing at
the code layer stops an autonomous self-modification session from
editing this file the way it could edit any other -- the real
protection right now is procedural: CLAUDE.md's Change workflow
requires backups/compile-checks/tests and human-visible diffs for
every change, and this file's own conspicuous header is a deliberate
tripwire for a human reviewing any diff that touches it.

A future phase (Phase 4, Guardian Financial Gate) should add a real
runtime self-check here -- e.g. hashing this file's contents at import
time and comparing against a value stored outside AI-writable reach,
halting all trading if it doesn't match -- so a silent edit is
detected rather than silently taking effect. Not implemented yet;
flagged explicitly rather than pretended to exist.

Nothing in this file is a suggestion. The risk engine (Phase 4) reads
these as hard limits, not defaults.
"""

# --- Capital ---------------------------------------------------------
STARTING_CAPITAL_ALLOCATION_GBP = 100.00

# --- Position / exposure limits ---------------------------------------
MAX_SINGLE_POSITION_VALUE_GBP = 20.00
MAX_TOTAL_MARKET_EXPOSURE_GBP = 80.00
MAX_OPEN_POSITIONS = 4

# --- Loss limits --------------------------------------------------------
MAX_DAILY_REALISED_LOSS_GBP = 5.00
MAX_WEEKLY_REALISED_LOSS_GBP = 15.00
MINIMUM_EQUITY_BEFORE_SHUTDOWN_GBP = 75.00

# --- Trade frequency ---------------------------------------------------
MAX_NEW_TRADES_PER_HOUR = 2
MAX_NEW_TRADES_PER_DAY = 8

# --- Instrument / product restrictions ---------------------------------
# The Trading 212 Public API only reaches Invest/Stocks-ISA accounts in
# the first place (confirmed via Phase 1 API research -- CFDs, margin,
# leverage, options, and derivatives are not reachable through this API
# at all, regardless of these flags). Kept explicit anyway so the risk
# engine has its own hard check rather than depending on that being
# permanently true of the broker's API surface.
LEVERAGE_DISABLED = True
MARGIN_DISABLED = True
CFDS_DISABLED = True
SHORT_SELLING_DISABLED = True
BORROWING_DISABLED = True
OPTIONS_DISABLED = True
DERIVATIVES_DISABLED = True
CRYPTO_CFDS_DISABLED = True


def as_dict() -> dict:
    """Read-only snapshot for the UI / audit log. Never used as a
    write path -- there isn't one."""
    return {
        "starting_capital_allocation_gbp": STARTING_CAPITAL_ALLOCATION_GBP,
        "max_single_position_value_gbp": MAX_SINGLE_POSITION_VALUE_GBP,
        "max_total_market_exposure_gbp": MAX_TOTAL_MARKET_EXPOSURE_GBP,
        "max_open_positions": MAX_OPEN_POSITIONS,
        "max_daily_realised_loss_gbp": MAX_DAILY_REALISED_LOSS_GBP,
        "max_weekly_realised_loss_gbp": MAX_WEEKLY_REALISED_LOSS_GBP,
        "minimum_equity_before_shutdown_gbp": MINIMUM_EQUITY_BEFORE_SHUTDOWN_GBP,
        "max_new_trades_per_hour": MAX_NEW_TRADES_PER_HOUR,
        "max_new_trades_per_day": MAX_NEW_TRADES_PER_DAY,
        "leverage_disabled": LEVERAGE_DISABLED,
        "margin_disabled": MARGIN_DISABLED,
        "cfds_disabled": CFDS_DISABLED,
        "short_selling_disabled": SHORT_SELLING_DISABLED,
        "borrowing_disabled": BORROWING_DISABLED,
        "options_disabled": OPTIONS_DISABLED,
        "derivatives_disabled": DERIVATIVES_DISABLED,
        "crypto_cfds_disabled": CRYPTO_CFDS_DISABLED,
    }
