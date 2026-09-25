"""
JarvisTrader (BETA) -- an autonomous AI trading experiment.

Ships as part of the normal Jarvis install, same as JarvisCode/
JarvisClipper. Each user connects their OWN Trading 212 account with
their OWN API keys and trades with their OWN money, entirely isolated
from every other user -- there is no shared capital, no shared
credentials, and no central execution of anyone else's trades. This is
real-money software; the UI and README both carry an explicit BETA /
"you are trading with real money at your own risk" notice, and every
install starts fully PAUSED with nothing connected until the owner of
that install deliberately sets it up.

Architecture (Phase 1 audit + design, see project conversation history):

    Market/Data Sources
            -> market/            (Phase 3+)
            -> strategy/          (Phase 6+)
            -> Jarvis Trading Brain (LLM, restricted tools only, Phase 9+)
            -> execution/intent.py (structured intent, schema-validated)
            -> risk/risk_engine.py (deterministic, AI cannot modify)
            -> risk/guardian_financial_gate.py (deny-by-default final gate)
            -> execution/execution_engine.py
            -> broker/trading212_client.py -> Trading 212 API
            -> broker/reconciliation.py
            -> memory/trader_database.py (positions, journal, audit log)

The AI proposes intent. Deterministic Python code controls execution,
risk limits, and broker access. The AI never receives Trading 212
credentials or a generic HTTP tool -- see security/credentials.py and
core/trader_core.py.

This is Phase 2: skeleton, UI shell, database, and the credential
layer only. No broker integration, no risk engine, no execution path,
and no LLM wiring exist yet -- those are later phases. Trading state
always starts DISABLED/PAUSED; nothing in this phase can place an
order because nothing here can talk to Trading 212 yet at all.
"""
