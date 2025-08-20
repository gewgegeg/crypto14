## CEX↔CEX Arbitrage Scanner (Binance, Kucoin, …)

This is a starter template for a centralized-exchange (CEX) inter-exchange arbitrage scanner inspired by P2P.Army and P2P Surfer. It:

- Loads and caches full spot market lists per exchange (similar to Coingecko market coverage)
- Fetches order books concurrently
- Computes fee-aware spreads (trading taker fees + on-chain withdrawal fee of the transferred base asset)
- Supports simple two-exchange arbitrage now, and includes a skeleton for 3–4 step multi-exchange routes
- Can notify via Telegram when profitable opportunities are found

### Quick start

1) Create a `.env` file (see `.env.example`).

2) Install Python deps (in this environment we used user-level pip):

```bash
python3 -m pip install -r /workspace/requirements.txt --break-system-packages
```

3) Update and cache markets:

```bash
python3 -c "from arbitrage.cli import main; import sys; sys.exit(main(['update-markets']))"
```

4) Dump markets for one exchange:

```bash
python3 -c "from arbitrage.cli import main; import sys; sys.exit(main(['dump-markets','--exchanges','kucoin']))"
```

5) Fetch sample order books for Kucoin:

```bash
python3 -c "from arbitrage.cli import main; import sys; sys.exit(main(['fetch-orderbooks','--exchange','kucoin','--sample','50']))"
```

6) Scan for simple two-exchange opportunities (adjust exchanges as available in your environment):

```bash
python3 -c "from arbitrage.cli import main; import sys; sys.exit(main(['scan-simple','--a','kucoin','--b','kraken']))"
```

### Architecture

- `arbitrage/config.py`: environment-driven settings
- `arbitrage/cache.py`: SQLite key-value cache for markets and generic blobs
- `arbitrage/exchanges/ccxt_client.py`: async ccxt connector, markets, orderbooks, fee data
- `arbitrage/fees.py`: VWAP and fee-aware profit math
- `arbitrage/scanner.py`: simple two-exchange scanner with concurrency and notifications
- `arbitrage/routes.py`: skeleton for 3–4 step multi-exchange routes
- `arbitrage/notify.py`: Telegram or console notifications
- `arbitrage/cli.py`: command-line entry points

### Notes

- Some exchanges block certain geographies; choose exchanges that are reachable from your runtime.
- Taker fees are sourced from exchange markets metadata when available; otherwise a conservative default is used.
- Withdrawal fees are estimated from per-currency network data and the cheapest common network shared by both exchanges.
