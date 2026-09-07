# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Hard rules (non-negotiable, apply to every task)

1. **`~/PycharmProjects/sysstra-*` repos are STRICTLY read-only.** Never edit, delete, rename,
   move, reformat, or write anything inside any `sysstra-*` folder — not even comments, logs, or
   "harmless" fixes. They are reference material for a live production system. Every change,
   without exception, happens inside `project-trigerr/` repos. If a fix seems needed on the
   sysstra side, note it in the task's output for Anurag — do not make it.
2. **No secrets in code or committed files** — not even as fallback defaults. Bootstrap secrets
   (`CONFIG_MONGO_URI`, `TENANT`) and credentials live only in local `.env` files (gitignored).
3. **Tenancy pattern is fixed**: config loads from the `platform_config` Mongo keyed by
   `(tenant, scope)` with per-tenant `configs_<tenant>` views, bootstrap via `CONFIG_MONGO_URI` +
   `TENANT`, offline fallback via `CONFIG_JSON_FILE`. Mirror
   `trigerr-trading-strategies/sts_config.py` — do not invent new config mechanisms.
4. **Do not touch live sysstra infrastructure**: never write to, repoint, or "test against" the
   production Mongo/Redis/S3/webhooks whose values appear in legacy config files. Verification
   uses local instances or `CONFIG_JSON_FILE` offline mode.
5. **Trigerr is a separate namespace product**: new code says `trigerr` (imports, service names,
   log names, DB/bucket seed values) — never introduce new `sysstra` identifiers.
6. Functions over classes; minimum code that solves the problem; surgical changes only.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```
## Project Overview

Trigerr is a Python library for algorithmic trading workflows supporting equities, derivatives, commodities, and crypto markets across global exchanges. The library provides unified interfaces for historical/live data fetching, order management (backtest/virtual/live), technical indicators, and trading utilities.

## Architecture

### Core Module Structure

- **trigerr/config.py**: Central configuration for API keys and service URLs (data_url, orders_url)
- **trigerr/data/**: Data fetching modules
  - `historical.py`: Historical OHLCV data via REST API (EOD, intraday, index, futures, options)
  - `live.py`: Real-time market data streaming
- **trigerr/orders/**: Order execution modules
  - `live.py`: Live trading order placement via broker APIs
  - `virtual.py`: Paper trading simulation
  - `backtest.py`: Backtesting engine with position tracking
  - `orders_utils.py`: Shared utilities for order management
- **trigerr/custom_indicators.py**: Custom technical indicators beyond pandas_ta (stochastic, VFI, swing calculations, etc.)
- **trigerr/trigerr_utils.py**: Core utility functions for trading operations (swing calculation, indicator application, PnL calculations, brokerage calculation, report generation)

### API-Driven Design

The library acts as a client to two primary backend services:
- **Data API** — sysstra-data-services (https://data.api.sysstra.com/), reached through the
  `sysstra_data` client package, which speaks its `/market-data/*` contract. Historical fetches
  go through `_get_client()` in `trigerr/data/historical.py`; reference lookups (symbols,
  expiries) through `trigerr/data/reference.py`.
- **Orders API** (https://api.orders.trigerr.com/): Handles order placement, position tracking, and broker integration

All data/order functions require API authentication via `x-api-key` header set through `trigerr.set_api_key()`.

> **Do not confuse the two data hosts.** `api.data.sysstra.com` is the *legacy* sysstra-data-api,
> serving the older `/fetch-*` routes; `data.api.sysstra.com` is sysstra-data-services, which this
> SDK targets. The names are transposed, the contracts are incompatible, and the migration kept no
> aliases — a `/fetch-*` path will not resolve on data-services.

> **The `sysstra_data` import is a deliberate, recorded exception to hard rule 5** (no new
> `sysstra` identifiers), decided 2026-09-07: trigerr consumes sysstra-data-services as-is and no
> `trigerr-data` package is planned. Keep the dependency confined to `_get_client()`.

### Key Patterns

1. **Configuration**: Users call `set_api_key()`, `set_data_url()`, `set_orders_url()` before using the library
2. **Data Fetching**: All historical data functions return lists of dictionaries (JSON responses from API)
3. **Order Management**: Orders are tracked in both Redis (cache) and MongoDB (persistence) on the backend
4. **Indicator Application**: `apply_indicators()` modifies DataFrames in-place, adding columns for each indicator
5. **Swing Calculation**: Complex swing detection algorithm in `calculate_swing()` identifies market structure changes

## Development Commands

### Installation
```bash
# Install in development mode
pip install -e .

# Install dependencies
pip install -r requirements.txt
```

### Building and Distribution
```bash
# Build distribution packages
python setup.py sdist bdist_wheel

# Install locally
pip install dist/trigerr-<version>.tar.gz
```

### Running Tests
```bash
# Run example scripts
python examples/orders_test.py
```

## Key Functions and Usage

### API Configuration
```python
import trigerr
trigerr.set_api_key("your-api-key")
```

### Data Fetching
- `fetch_eod_candles(symbol, start_date, end_date, exchange)`: Daily OHLCV data
- `fetch_index_candles(symbol, start_date, end_date, granularity, exchange)`: Intraday index data
- `fetch_futures_candle(underlying, start_date, end_date, granularity)`: Futures historical data
- `fetch_option_candles(underlying, start_date, end_date, option_type, strike_price, expiry)`: Options chain data

All dates should be passed as datetime.date or strings in YYYY-MM-DD format.

### Technical Analysis
- `apply_indicators(dataframe, indicators_dict)`: Apply multiple indicators to OHLCV DataFrame
  - Supports 40+ indicators: EMA, SMA, RSI, MACD, ADX, Bollinger Bands, ATR, Stochastic, etc.
  - indicators_dict format: `{"RSI": {"length": 14}, "EMA": {"length": 20}}`
- `calculate_swing(df, swing_setup=2)`: Detect swing highs/lows and trend changes
- `change_granularity(data_df, granularity)`: Convert minute-level data to higher timeframes

### Order Execution
- `place_lt_order(symbol, exchange, quantity, transaction_type, order_type, credential_id, ...)`: Place live orders
  - Supports EQUITY, OPTIONS, FUTURES across NSE/BSE exchanges
  - Order types: MARKET, LIMIT, STOPLOSS
  - Returns (status, response_dict)

### Utility Functions
- `calculate_brokerage(buy_price, sell_price, quantity, broker, market_type, ...)`: Calculate fees and net PnL
  - Supports Zerodha, Binance, CoinDCX, Schwab brokers
- `generate_mt_report(report_df, pnl_column)`: Generate MetaTrader-style backtest reports with drawdown, win rate, etc.
- `round_to_tick_multiple(input_price)`: Round prices to NSE tick size (0.05)
- `calculate_liquidation_price(entry_price, leverage, position_type)`: For margin/futures positions

## Important Notes

### Data Format Conventions
- OHLCV DataFrames use lowercase column names: `open`, `high`, `low`, `close`, `volume`
- Timestamps are stored in `timestamp` column as datetime objects
- Options data includes: `underlying_stock`, `strike`, `option_type`, `expiry` columns

### Swing Calculation
The `calculate_swing()` function is central to many strategies:
- Identifies structural highs/lows based on candle closes
- Adds `swing` column ("UP"/"DOWN") and `swing_change` (boolean) to DataFrame
- `swing_setup` parameter controls sensitivity (default=2 means 2-bar confirmation)
- Handles outside bars and complex reversal patterns

### Granularity Values
- 1 = 1 minute
- 5 = 5 minutes
- 15 = 15 minutes
- 60 = 1 hour
- Use `change_granularity()` to convert between timeframes

### Brokerage Calculations
The `calculate_brokerage()` function accounts for:
- STT (Securities Transaction Tax)
- Exchange transaction fees
- GST
- SEBI charges
- Stamp duty
- Broker-specific fee structures

Returns tuple: (total_charges, net_pnl)

### Position Management
- Positions are tracked by `position_type` ("LONG" or "SHORT")
- Entry/exit logic in backtesting uses `trade_action` ("ENTRY" or "EXIT")
- Multiple exit types supported: "TARGET", "STOPLOSS", "TIME_EXIT", "SIGNAL_EXIT"

## Dependencies

Core: requests, numpy, pandas, pandas_ta, redis

The library requires pandas_ta for technical indicators - ensure it's installed before using `apply_indicators()`.

## Market Support

- **Indian Markets**: NSE, BSE (primary focus)
- **US Markets**: NYSE, NASDAQ (via Schwab integration)
- **Crypto**: Binance, CoinDCX

Exchange parameter defaults to "NSE" for Indian markets, "XNSE" for data API calls.
