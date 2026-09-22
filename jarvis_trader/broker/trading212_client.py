"""
Trading212Client -- placeholder for Phase 3 (read-only integration).

Not implemented yet. Will wrap the confirmed real Trading 212 Public
API endpoints only (Phase 1 research): equity/account/summary,
equity/account/cash, equity/positions, equity/orders, equity/orders/
{id}, equity/orders/market|limit|stop|stop_limit, equity/metadata/
instruments, equity/metadata/exchanges, equity/history/orders,
history/dividends, history/transactions -- never an invented endpoint.

Reads security/credentials.py for API key/secret; the LLM never calls
this module directly (see jarvis_trader/__init__.py's architecture
note) -- only a restricted tool-function layer (later phase) does.
"""
