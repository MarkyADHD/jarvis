"""
Strategy schema -- a strategy is never silently mutated while it's
being evaluated (per the design). Changing parameters means creating
a new version (new strategy_id), never overwriting an existing row.
"""
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class StrategyStatus(str, Enum):
    EXPERIMENTAL = "EXPERIMENTAL"
    BACKTESTING = "BACKTESTING"
    PAPER_TESTING = "PAPER_TESTING"
    APPROVED_FOR_LIVE = "APPROVED_FOR_LIVE"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"


@dataclass
class Strategy:
    strategy_id: str
    name: str
    version: str
    description: str = ""
    parameters: dict = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    creator_model: str = "template"
    status: str = StrategyStatus.EXPERIMENTAL.value
    backtest_results: Optional[dict] = None
    paper_trading_results: Optional[dict] = None
    live_results: Optional[dict] = None

    def as_db_row(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "parameters_json": json.dumps(self.parameters),
            "created_at": self.created_at,
            "creator_model": self.creator_model,
            "status": self.status,
            "backtest_results_json": json.dumps(self.backtest_results) if self.backtest_results else None,
            "paper_trading_results_json": json.dumps(self.paper_trading_results) if self.paper_trading_results else None,
            "live_results_json": json.dumps(self.live_results) if self.live_results else None,
        }

    @staticmethod
    def from_db_row(row) -> "Strategy":
        return Strategy(
            strategy_id=row["strategy_id"],
            name=row["name"],
            version=row["version"],
            description=row["description"] or "",
            parameters=json.loads(row["parameters_json"]) if row["parameters_json"] else {},
            created_at=row["created_at"],
            creator_model=row["creator_model"] or "template",
            status=row["status"],
            backtest_results=json.loads(row["backtest_results_json"]) if row["backtest_results_json"] else None,
            paper_trading_results=json.loads(row["paper_trading_results_json"]) if row["paper_trading_results_json"] else None,
            live_results=json.loads(row["live_results_json"]) if row["live_results_json"] else None,
        )
