from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import List, Optional

from .config import settings, Settings
from .scanner import ArbitrageScanner
from .utils import get_logger

logger = get_logger("cli")


def use_uvloop_if_available() -> None:
    try:
        import uvloop  # type: ignore

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    except Exception:  # noqa: BLE001
        pass


async def cmd_update_markets(args, cfg: Settings):
    scanner = ArbitrageScanner(cfg)
    # Update markets for all configured exchanges
    for ex in cfg.exchanges:
        from .exchanges import create_exchange, load_all_markets

        e = await create_exchange(ex, cfg)
        try:
            try:
                markets = await load_all_markets(e, scanner.market_cache, cfg.markets_ttl_seconds)
                logger.info("Loaded markets for %s: %d spot symbols", e.id, len(markets))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Failed loading markets for %s: %s", ex, exc)
        finally:
            try:
                await e.close()
            except Exception:  # noqa: BLE001
                pass
    print("Markets update attempted for:", ", ".join(cfg.exchanges))


async def cmd_scan_simple(args, cfg: Settings):
    scanner = ArbitrageScanner(cfg)
    a = args.a or cfg.exchanges[0]
    b = args.b or (cfg.exchanges[1] if len(cfg.exchanges) > 1 else None)
    if not b:
        print("Please specify two exchanges via --a and --b or set EXCHANGES env")
        sys.exit(1)
    await scanner.scan_two_exchanges(a, b)


async def cmd_dump_markets(args, cfg: Settings):
    from .exchanges import create_exchange, load_all_markets
    from .cache import MarketCache

    cache = MarketCache(cfg.cache_db_path)
    exchanges: List[str] = args.exchanges or list(cfg.exchanges)

    result = {}
    for ex in exchanges:
        e = await create_exchange(ex, cfg)
        try:
            markets = await load_all_markets(e, cache, cfg.markets_ttl_seconds)
            result[e.id] = markets
            logger.info("%s: %d spot markets", e.id, len(markets))
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s: failed to load markets: %s", ex, exc)
        finally:
            try:
                await e.close()
            except Exception:  # noqa: BLE001
                pass

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"Saved markets to {args.out}")
    else:
        # Print a short summary
        for ex, mkts in result.items():
            print(f"{ex}: {len(mkts)} spot markets cached")


async def cmd_fetch_orderbooks(args, cfg: Settings):
    from .exchanges import create_exchange, load_all_markets, fetch_order_book_safe
    from .utils import AsyncLimiter

    ex_id: str = args.exchange
    e = await create_exchange(ex_id, cfg)
    try:
        markets = await load_all_markets(e, ArbitrageScanner(cfg).market_cache, cfg.markets_ttl_seconds)
        symbols = [m["symbol"] for m in markets]
        if args.sample and args.sample > 0:
            symbols = symbols[: args.sample]
        limiter = AsyncLimiter(cfg.concurrency)
        count = 0

        async def worker(sym: str):
            nonlocal count
            async with limiter:
                ob = await fetch_order_book_safe(e, sym, limit=cfg.orderbook_limit)
                if ob and ob.get("bids") and ob.get("asks"):
                    count += 1

        await asyncio.gather(*[worker(s) for s in symbols])
        print(f"Fetched {count}/{len(symbols)} orderbooks for {e.id}")
    finally:
        try:
            await e.close()
        except Exception:  # noqa: BLE001
            pass


def main(argv: list[str] | None = None) -> int:
    use_uvloop_if_available()

    parser = argparse.ArgumentParser(description="CEX<->CEX Arbitrage Scanner")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_update = sub.add_parser("update-markets", help="Load and cache all markets for configured exchanges")
    p_update.set_defaults(func=cmd_update_markets)

    p_scan = sub.add_parser("scan-simple", help="Scan two exchanges for fee-aware arbitrage opportunities")
    p_scan.add_argument("--a", type=str, default=None, help="Buy-side exchange id (e.g., binance)")
    p_scan.add_argument("--b", type=str, default=None, help="Sell-side exchange id (e.g., kucoin)")
    p_scan.set_defaults(func=cmd_scan_simple)

    p_dump = sub.add_parser("dump-markets", help="Dump cached markets for specified exchanges (or configured ones)")
    p_dump.add_argument("--exchanges", nargs="*", help="List of exchange ids to dump (default from EXCHANGES)")
    p_dump.add_argument("--out", type=str, default=None, help="Optional JSON output path")
    p_dump.set_defaults(func=cmd_dump_markets)

    p_ob = sub.add_parser("fetch-orderbooks", help="Fetch order books for all (or sampled) markets on an exchange")
    p_ob.add_argument("--exchange", required=True, help="Exchange id, e.g., kucoin, bybit, kraken")
    p_ob.add_argument("--sample", type=int, default=200, help="Limit to first N symbols (0=all)")
    p_ob.set_defaults(func=cmd_fetch_orderbooks)

    args = parser.parse_args(argv)

    async def runner():
        await args.func(args, settings)

    asyncio.run(runner())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())