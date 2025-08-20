from __future__ import annotations

from typing import Dict, List, Optional, Tuple


def compute_vwap_for_amount(side: str, levels: List[List[float]], amount_base: float) -> Optional[Tuple[float, float]]:
    """
    Compute VWAP price and filled amount for the requested base amount.

    side: "buy" -> consumes asks; "sell" -> consumes bids
    levels: order book side [[price, amount, ...], ...]
    amount_base: amount of base asset to buy/sell
    Returns: (avg_price, filled_amount)
    """
    if amount_base <= 0:
        return None
    remaining = float(amount_base)
    total_quote = 0.0
    filled = 0.0
    for level in levels:
        if not level or len(level) < 2:
            continue
        try:
            price = float(level[0])
            amount = float(level[1])
        except Exception:  # noqa: BLE001
            continue
        if amount <= 0 or price <= 0:
            continue
        take = min(remaining, amount)
        total_quote += take * price
        remaining -= take
        filled += take
        if remaining <= 1e-12:
            break
    if filled <= 0:
        return None
    avg_price = total_quote / filled
    return avg_price, filled


def estimate_fee_aware_profit_pct(
    buy_price: float,
    sell_price: float,
    base_amount: float,
    taker_fee_buy: float,
    taker_fee_sell: float,
    withdraw_fee_base: float,
) -> float:
    """
    Estimate percentage profit for buy -> withdraw -> sell (same base/quote on two exchanges).

    - buy_price, sell_price: average prices from order book for the trade sizes
    - base_amount: base units bought
    - withdraw_fee_base: base units charged by network withdrawal from the buy-side exchange
    Returns: profit_percent
    """
    cost_quote = base_amount * buy_price
    cost_quote_with_fee = cost_quote * (1.0 + taker_fee_buy)

    base_after_withdraw = max(0.0, base_amount - withdraw_fee_base)
    revenue_quote = base_after_withdraw * sell_price
    revenue_quote_after_fee = revenue_quote * (1.0 - taker_fee_sell)

    if cost_quote_with_fee <= 0:
        return -100.0
    profit_pct = (revenue_quote_after_fee - cost_quote_with_fee) / cost_quote_with_fee * 100.0
    return profit_pct