from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from tabulate import tabulate

from .cache import MarketCache
from .config import Settings
from .exchanges import (
    create_exchange,
    fetch_order_book_safe,
    find_cheapest_common_network_fee,
    find_common_symbols,
    get_taker_fee_for_market,
    load_all_markets,
)
from .fees import compute_vwap_for_amount, estimate_fee_aware_profit_pct
from .notify import Notifier
from .utils import AsyncLimiter, get_logger

logger = get_logger("scanner")


@dataclass
class Opportunity:
    symbol: str
    buy_exchange: str
    sell_exchange: str
    profit_pct: float
    base_amount: float
    buy_price: float
    sell_price: float
    network: Optional[str]


class ArbitrageScanner:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.market_cache = MarketCache(settings.cache_db_path)
        self.notifier = Notifier()

    async def _prepare_exchanges(self, a: str, b: str):
        ex_a = await create_exchange(a, self.settings)
        ex_b = await create_exchange(b, self.settings)
        return ex_a, ex_b

    async def _load_common_symbols(self, ex_a, ex_b) -> Tuple[List[Dict], List[Dict], List[str]]:
        markets_a, markets_b = await asyncio.gather(
            load_all_markets(ex_a, self.market_cache, self.settings.markets_ttl_seconds),
            load_all_markets(ex_b, self.market_cache, self.settings.markets_ttl_seconds),
        )
        symbols = find_common_symbols(markets_a, markets_b, self.settings.preferred_quotes)
        return markets_a, markets_b, symbols

    async def _fetch_orderbooks_for_symbols(self, ex, symbols: List[str]) -> Dict[str, Optional[Dict]]:
        limiter = AsyncLimiter(self.settings.concurrency)
        results: Dict[str, Optional[Dict]] = {}

        async def worker(sym: str):
            async with limiter:
                ob = await fetch_order_book_safe(ex, sym, limit=self.settings.orderbook_limit)
                results[sym] = ob

        await asyncio.gather(*[worker(s) for s in symbols])
        return results

    async def scan_two_exchanges(self, a: str, b: str) -> List[Opportunity]:
        ex_a, ex_b = await self._prepare_exchanges(a, b)
        try:
            markets_a, markets_b, symbols = await self._load_common_symbols(ex_a, ex_b)
            if not symbols:
                logger.warning("No common symbols between %s and %s", ex_a.id, ex_b.id)
                return []

            logger.info("Common symbols for %s-%s (quotes=%s): %d", ex_a.id, ex_b.id, ",".join(self.settings.preferred_quotes), len(symbols))

            # Index markets by symbol for fee access
            idx_a = {m["symbol"]: m for m in markets_a}
            idx_b = {m["symbol"]: m for m in markets_b}

            # Fetch order books concurrently on both exchanges
            books_a_task = asyncio.create_task(self._fetch_orderbooks_for_symbols(ex_a, symbols))
            books_b_task = asyncio.create_task(self._fetch_orderbooks_for_symbols(ex_b, symbols))
            books_a, books_b = await asyncio.gather(books_a_task, books_b_task)

            # Find network fee per base asset if possible (best common network)
            # We'll lazily compute per base when needed
            network_fee_cache: Dict[str, Tuple[Optional[str], float]] = {}

            opportunities: List[Opportunity] = []

            for sym in symbols:
                ob_a = books_a.get(sym)
                ob_b = books_b.get(sym)
                if not ob_a or not ob_b:
                    continue
                base, quote = sym.split("/")
                if quote.upper() not in set(q.upper() for q in self.settings.preferred_quotes):
                    continue

                taker_a = get_taker_fee_for_market(ex_a.id, idx_a[sym])
                taker_b = get_taker_fee_for_market(ex_b.id, idx_b[sym])

                # Base amount sized by target notional in quote on buy side
                best_ask = ob_a.get("asks") or []
                best_bid = ob_b.get("bids") or []
                if not best_ask or not best_bid:
                    continue

                # Compute VWAP for buying on A and selling on B
                # First estimate base amount via top-of-book ask on A
                top_ask = best_ask[0][0]
                target_quote = float(self.settings.min_notional_usd)
                est_base_amount = max(1e-6, target_quote / float(top_ask))
                buy_vwap = compute_vwap_for_amount("buy", best_ask, est_base_amount)
                sell_vwap = compute_vwap_for_amount("sell", best_bid, est_base_amount)
                if not buy_vwap or not sell_vwap:
                    continue
                buy_avg, buy_filled = buy_vwap
                sell_avg, sell_filled = sell_vwap
                base_amount = min(buy_filled, sell_filled)
                if base_amount <= 0:
                    continue

                # Network fee for transferring base from A to B
                if base not in network_fee_cache:
                    net = await find_cheapest_common_network_fee(ex_a, ex_b, base)
                    network_fee_cache[base] = (net[0], net[1]) if net else (None, 0.0)
                network_name, withdraw_fee_base = network_fee_cache[base]

                profit_ab = estimate_fee_aware_profit_pct(
                    buy_price=buy_avg,
                    sell_price=sell_avg,
                    base_amount=base_amount,
                    taker_fee_buy=taker_a,
                    taker_fee_sell=taker_b,
                    withdraw_fee_base=withdraw_fee_base,
                )
                if profit_ab >= self.settings.min_profit_pct:
                    opportunities.append(
                        Opportunity(
                            symbol=sym,
                            buy_exchange=ex_a.id,
                            sell_exchange=ex_b.id,
                            profit_pct=profit_ab,
                            base_amount=base_amount,
                            buy_price=buy_avg,
                            sell_price=sell_avg,
                            network=network_name,
                        )
                    )

                # Reverse direction B -> A
                best_ask_b = ob_b.get("asks") or []
                best_bid_a = ob_a.get("bids") or []
                if best_ask_b and best_bid_a:
                    top_ask_b = best_ask_b[0][0]
                    est_base_amount_b = max(1e-6, target_quote / float(top_ask_b))
                    buy_vwap_b = compute_vwap_for_amount("buy", best_ask_b, est_base_amount_b)
                    sell_vwap_a = compute_vwap_for_amount("sell", best_bid_a, est_base_amount_b)
                    if buy_vwap_b and sell_vwap_a:
                        buy_avg_b, buy_filled_b = buy_vwap_b
                        sell_avg_a, sell_filled_a = sell_vwap_a
                        base_amount_b = min(buy_filled_b, sell_filled_a)
                        if base not in network_fee_cache:
                            net2 = await find_cheapest_common_network_fee(ex_b, ex_a, base)
                            network_fee_cache[base] = (net2[0], net2[1]) if net2 else (None, 0.0)
                        network_name2, withdraw_fee_base2 = network_fee_cache[base]
                        taker_b_buy = taker_b
                        taker_a_sell = taker_a
                        profit_ba = estimate_fee_aware_profit_pct(
                            buy_price=buy_avg_b,
                            sell_price=sell_avg_a,
                            base_amount=base_amount_b,
                            taker_fee_buy=taker_b_buy,
                            taker_fee_sell=taker_a_sell,
                            withdraw_fee_base=withdraw_fee_base2,
                        )
                        if profit_ba >= self.settings.min_profit_pct:
                            opportunities.append(
                                Opportunity(
                                    symbol=sym,
                                    buy_exchange=ex_b.id,
                                    sell_exchange=ex_a.id,
                                    profit_pct=profit_ba,
                                    base_amount=base_amount_b,
                                    buy_price=buy_avg_b,
                                    sell_price=sell_avg_a,
                                    network=network_name2,
                                )
                            )

            opportunities.sort(key=lambda o: o.profit_pct, reverse=True)

            if opportunities:
                headers = [
                    "Symbol",
                    "Buy@",
                    "Sell@",
                    "Profit %",
                    "Base Amt",
                    "Buy Px",
                    "Sell Px",
                    "Network",
                ]
                rows = [
                    [
                        o.symbol,
                        o.buy_exchange,
                        o.sell_exchange,
                        f"{o.profit_pct:.3f}",
                        f"{o.base_amount:.6f}",
                        f"{o.buy_price:.6f}",
                        f"{o.sell_price:.6f}",
                        o.network or "?",
                    ]
                    for o in opportunities
                ]
                print(tabulate(rows, headers=headers, tablefmt="github"))

                # Optional notification of the best few opportunities
                top = opportunities[:3]
                for opp in top:
                    msg = (
                        f"Arb {opp.symbol}: buy {opp.buy_exchange} @ {opp.buy_price:.6f} -> "
                        f"sell {opp.sell_exchange} @ {opp.sell_price:.6f} | "
                        f"profit {opp.profit_pct:.3f}% | amt {opp.base_amount:.6f} | net {opp.network or '?'}"
                    )
                    try:
                        await self.notifier.send(msg)
                    except Exception:  # noqa: BLE001
                        pass
            else:
                logger.info("No opportunities >= %.3f%% found for %s-%s", self.settings.min_profit_pct, ex_a.id, ex_b.id)

            return opportunities
        finally:
            # Ensure HTTP sessions are closed
            try:
                await ex_a.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                await ex_b.close()
            except Exception:  # noqa: BLE001
                pass