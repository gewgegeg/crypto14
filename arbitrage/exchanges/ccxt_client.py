from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional, Tuple

import ccxt.async_support as ccxt  # type: ignore

from ..config import Settings
from ..utils import get_logger

logger = get_logger("exchanges")


def _maybe_get_exchange_class(exchange_id: str):
    if not hasattr(ccxt, exchange_id):
        raise ValueError(f"Unsupported exchange id: {exchange_id}")
    return getattr(ccxt, exchange_id)


async def create_exchange(exchange_id: str, settings: Settings) -> ccxt.Exchange:
    exchange_id = exchange_id.lower()
    exchange_class = _maybe_get_exchange_class(exchange_id)
    kwargs: Dict[str, Any] = {
        "enableRateLimit": True,
        "timeout": 20000,
        "options": {
            "adjustForTimeDifference": True,
        },
    }

    # Minimal key wiring (public endpoints do not need keys)
    if exchange_id == "binance":
        if settings.binance_key and settings.binance_secret:
            kwargs.update({"apiKey": settings.binance_key, "secret": settings.binance_secret})
    elif exchange_id == "kucoin":
        if settings.kucoin_key and settings.kucoin_secret and settings.kucoin_password:
            kwargs.update(
                {
                    "apiKey": settings.kucoin_key,
                    "secret": settings.kucoin_secret,
                    "password": settings.kucoin_password,
                }
            )

    exchange: ccxt.Exchange = exchange_class(kwargs)
    return exchange


async def load_all_markets(
    exchange: ccxt.Exchange,
    markets_cache,
    ttl_seconds: int,
) -> List[Dict[str, Any]]:
    cached = markets_cache.load_cached_markets(exchange.id, ttl_seconds)
    if cached is not None:
        return cached

    await exchange.load_markets()  # populates exchange.markets

    markets: List[Dict[str, Any]] = []
    for market in exchange.markets.values():
        if not market.get("spot", True):
            continue
        if market.get("active") is False:
            continue
        markets.append(
            {
                "symbol": market["symbol"],
                "base": market["base"],
                "quote": market["quote"],
                "taker": float(market.get("taker") or exchange.fees.get("trading", {}).get("taker", 0.001)),
                "active": bool(market.get("active", True)),
            }
        )

    markets_cache.save_markets(exchange.id, markets)
    return markets


async def fetch_order_book_safe(
    exchange: ccxt.Exchange,
    symbol: str,
    limit: int = 50,
) -> Optional[Dict[str, Any]]:
    # Try with requested limit
    try:
        return await exchange.fetch_order_book(symbol, limit=limit)
    except Exception as exc1:  # noqa: BLE001
        msg = str(exc1)
        # Some exchanges (e.g., Kucoin) only allow specific limits (20 or 100)
        candidates: List[Optional[int]] = []
        if exchange.id in ("kucoin", "kucoinfutures"):
            candidates = [20, 100]
        elif "limit" in msg and any(x in msg for x in ["20", "50", "100", "500", "1000"]):
            candidates = [20, 50, 100]
        else:
            candidates = [None]
        for cand in candidates:
            try:
                if cand is None:
                    return await exchange.fetch_order_book(symbol)
                return await exchange.fetch_order_book(symbol, limit=cand)
            except Exception:  # noqa: BLE001
                continue
        logger.warning("%s fetch_order_book(%s) failed: %s", exchange.id, symbol, exc1)
        return None


def get_taker_fee_for_market(exchange_id: str, market: Dict[str, Any]) -> float:
    rate = float(market.get("taker", 0.001))
    # Safety clamp
    if rate < 0:
        rate = 0.0
    if rate > 0.02:  # unlikely higher than 2%
        rate = 0.02
    return rate


def find_common_symbols(
    markets_a: List[Dict[str, Any]],
    markets_b: List[Dict[str, Any]],
    preferred_quotes: Optional[Tuple[str, ...]] = None,
) -> List[str]:
    set_a = {(m["base"], m["quote"]) for m in markets_a if m.get("active", True)}
    set_b = {(m["base"], m["quote"]) for m in markets_b if m.get("active", True)}
    common = set_a & set_b
    symbols = [f"{base}/{quote}" for base, quote in common]
    if preferred_quotes:
        quotes = set(q.upper() for q in preferred_quotes)
        symbols = [s for s in symbols if s.split("/")[1].upper() in quotes]
    symbols.sort()
    return symbols


async def _extract_currency_network_fees(exchange: ccxt.Exchange) -> Dict[str, Dict[str, float]]:
    # Returns mapping: currency_code -> { network_name -> withdraw_fee_in_currency }
    try:
        currencies = await exchange.fetch_currencies()
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s fetch_currencies failed: %s", exchange.id, exc)
        return {}

    result: Dict[str, Dict[str, float]] = {}
    for code, data in (currencies or {}).items():
        network_fees: Dict[str, float] = {}
        networks = data.get("networks") or {}
        for net_name, net_data in networks.items():
            fee = None
            if isinstance(net_data, dict):
                fee = net_data.get("withdrawFee")
                if fee is None:
                    fee = net_data.get("fee")
            if fee is None:
                continue
            try:
                fee = float(fee)
            except Exception:  # noqa: BLE001
                continue
            network_fees[net_name] = fee
        if network_fees:
            result[code] = network_fees
    return result


async def find_cheapest_common_network_fee(
    exchange_a: ccxt.Exchange,
    exchange_b: ccxt.Exchange,
    currency_code: str,
) -> Optional[Tuple[str, float]]:
    fees_a, fees_b = await asyncio.gather(
        _extract_currency_network_fees(exchange_a),
        _extract_currency_network_fees(exchange_b),
    )
    a = fees_a.get(currency_code) or {}
    b = fees_b.get(currency_code) or {}
    if not a or not b:
        return None
    common_networks = set(a.keys()) & set(b.keys())
    if not common_networks:
        return None
    # Pick the lowest fee network, tie-breaking by a simple alphabetical order
    best_network = min(common_networks, key=lambda n: (a.get(n, float("inf")) + b.get(n, 0.0)))
    return best_network, float(a[best_network])