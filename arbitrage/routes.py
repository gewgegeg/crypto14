from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class RouteStep:
    kind: str  # "trade" or "transfer"
    exchange_id: Optional[str] = None  # for trade
    symbol: Optional[str] = None  # e.g., "BTC/USDT" for trade
    action: Optional[str] = None  # "buy" or "sell"
    network: Optional[str] = None  # for transfer
    asset: Optional[str] = None  # base currency for transfer
    from_exchange: Optional[str] = None
    to_exchange: Optional[str] = None


@dataclass
class Route:
    steps: List[RouteStep]


class RouteEvaluator:
    """
    Skeleton for evaluating multi-step (3-4 step) arbitrage routes.
    Intended extension points:
    - Price sourcing via order books (VWAP per step)
    - Per-exchange taker fees
    - Per-network withdrawal fees and delays
    - Liquidity/amount sizing across steps
    """

    def __init__(self, settings):
        self.settings = settings

    async def evaluate(self, starting_quote_amount: float, route: Route):
        """
        Evaluate the route returns given a starting notional in quote currency.
        This is a placeholder to be implemented with actual exchange connectors.
        """
        # For now, provide a stub that simply returns the input.
        return {
            "route": route,
            "start": starting_quote_amount,
            "end": starting_quote_amount,  # Replace with computed final after applying steps
            "profit_pct": 0.0,
        }