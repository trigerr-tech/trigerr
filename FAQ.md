# Frequently Asked Questions (FAQ)

Common questions and solutions for using Sysstra.

---

## Table of Contents

- [Getting Started](#getting-started)
- [Installation & Setup](#installation--setup)
- [Data & Market Access](#data--market-access)
- [Technical Indicators](#technical-indicators)
- [Order Placement](#order-placement)
- [Backtesting](#backtesting)
- [Performance & Optimization](#performance--optimization)
- [Errors & Troubleshooting](#errors--troubleshooting)
- [Pricing & Limits](#pricing--limits)

---

## Getting Started

### What is Sysstra?

Sysstra is a Python library for algorithmic trading that provides:
- Historical and real-time market data
- Order execution across multiple brokers
- 40+ technical indicators
- Backtesting and paper trading
- Performance analytics

### Who is it for?

- Quantitative traders developing algorithmic strategies
- Retail traders wanting to automate their trading
- Researchers analyzing market data
- Students learning algorithmic trading
- Portfolio managers backtesting strategies

### Which markets are supported?

- **Indian Markets**: NSE, BSE (equities, futures, options)
- **US Markets**: NYSE, NASDAQ, options
- **Crypto**: Binance, CoinDCX (spot, futures)

### Do I need a broker account?

- **For Data**: You need a Sysstra API key (data access)
- **For Live Trading**: You need both Sysstra API key and broker account
- **For Backtesting**: Only Sysstra API key required
- **For Paper Trading**: Only Sysstra API key required

---

## Installation & Setup

### How do I install Sysstra?

```bash
pip install sysstra
```

### What are the dependencies?

Core dependencies are automatically installed:
- `requests` - API communication
- `numpy` - Numerical operations
- `pandas` - Data manipulation
- `pandas_ta` - Technical analysis
- `redis` - Order caching (for live trading)

### How do I get an API key?

1. Visit https://sysstra.com/signup
2. Create an account
3. Verify your email
4. Navigate to API Settings
5. Generate an API key

### How do I configure my API key?

```python
import sysstra

# Method 1: Direct (not recommended for production)
sysstra.set_api_key("your-api-key")

# Method 2: Environment variable (recommended)
import os
from dotenv import load_dotenv

load_dotenv()
sysstra.set_api_key(os.getenv('SYSSTRA_API_KEY'))
```

### How do I update Sysstra?

```bash
pip install --upgrade sysstra
```

---

## Data & Market Access

### How much historical data can I fetch?

Depends on your plan:
- **Free**: Last 30 days
- **Basic**: Last 1 year
- **Pro**: Last 5 years
- **Enterprise**: Full history (varies by market)

### What granularity options are available?

- 1 minute
- 5 minutes
- 15 minutes
- 30 minutes
- 60 minutes (1 hour)
- Daily (use `fetch_eod_candles()`)

### Can I fetch data for multiple symbols at once?

Currently, you need to loop through symbols:

```python
symbols = ["RELIANCE", "TCS", "INFY"]
all_data = {}

for symbol in symbols:
    data = fetch_eod_candles(symbol, start_date, end_date)
    all_data[symbol] = data
```

We're working on bulk fetch support in v0.2.0.

### How do I handle missing data?

```python
import pandas as pd

df = pd.DataFrame(candles_data)

# Check for missing data
print(df.isnull().sum())

# Forward fill missing values
df.fillna(method='ffill', inplace=True)

# Or drop missing rows
df.dropna(inplace=True)
```

### What timezone is the data in?

- **Indian Markets**: IST (UTC+5:30)
- **US Markets**: EST/EDT (UTC-5/-4)
- **Crypto**: UTC

Convert timezones:
```python
df['timestamp'] = pd.to_datetime(df['timestamp'])
df['timestamp'] = df['timestamp'].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
```

### Why am I getting empty data?

Common reasons:
1. **Market Closed**: No data on weekends/holidays
2. **Invalid Symbol**: Check symbol format (e.g., "NIFTY 50" not "NIFTY50")
3. **Future Date**: Can't fetch data for future dates
4. **API Key**: Invalid or expired API key
5. **Rate Limit**: Too many requests

Check:
```python
data = fetch_eod_candles(symbol, start, end)
if not data:
    print("No data returned - check symbol, dates, and API key")
```

---

## Technical Indicators

### How many indicators can I apply at once?

There's no hard limit, but performance degrades with many indicators:
- **1-10 indicators**: Fast
- **10-20 indicators**: Moderate
- **20+ indicators**: Slower, consider optimization

### Can I create custom indicators?

Yes! Add to `sysstra/custom_indicators.py`:

```python
def my_custom_indicator(dataframe, param1, param2):
    """Your custom indicator logic"""
    result = # your calculation
    return result
```

Then add to `apply_indicators()` in `sysstra_utils.py`:

```python
if "CUSTOM" in indicators_dict:
    custom_values = my_custom_indicator(
        dataframe, 
        indicators_dict["CUSTOM"]["param1"],
        indicators_dict["CUSTOM"]["param2"]
    )
    dataframe["custom"] = custom_values
```

### Why are my indicator values NaN?

Indicators need a "warmup period":
- RSI(14) needs 14 candles before first value
- EMA(20) needs 20 candles before accurate values
- MACD needs ~35 candles (slow period)

Solution:
```python
# Fetch extra data for warmup
start_date = start_date - timedelta(days=50)

# Apply indicators
df = apply_indicators(df, indicators)

# Remove warmup period
df = df[df['timestamp'] >= original_start_date]
```

### How do I combine multiple indicators?

```python
indicators = {
    "RSI": {"length": 14},
    "EMA20": {"length": 20},
    "EMA50": {"length": 50},
    "MACD": {
        "source": "close",
        "fast_length": 12,
        "slow_length": 26,
        "signal_smoothing": 9
    }
}

df = apply_indicators(df, indicators)

# Combine conditions
df['buy_signal'] = (
    (df['rsi'] < 30) &
    (df['close'] > df['ema20']) &
    (df['ema20'] > df['ema50']) &
    (df['macd'] > df['macd_s'])
)
```

### Which indicator is best for trend detection?

Popular choices:
- **ADX**: Measures trend strength (>25 = strong trend)
- **Supertrend**: Clear trend direction with support/resistance
- **EMA Crossover**: EMA(20) vs EMA(50)
- **DMI**: Directional movement

No single "best" indicator - combine multiple for confirmation.

---

## Order Placement

### How do I place a live order?

```python
from sysstra.orders import place_lt_order

status, response = place_lt_order(
    symbol="RELIANCE",
    exchange="NSE",
    quantity=10,
    lot_size=1,
    transaction_type="BUY",
    order_type="MARKET",
    asset_type="EQUITY",
    holding_type="INTRADAY",
    credential_id="your-credential-id"
)

if status == "success":
    print(f"Order ID: {response['order_id']}")
else:
    print(f"Error: {response['message']}")
```

### What order types are supported?

- **MARKET**: Execute immediately at best available price
- **LIMIT**: Execute only at specified price or better
- **STOPLOSS**: Trigger order when price hits trigger_price

```python
# Limit order
place_lt_order(..., order_type="LIMIT", order_price=1500.00)

# Stop loss order
place_lt_order(..., order_type="STOPLOSS", trigger_price=1450.00)
```

### How do I check order status?

```python
from sysstra.orders import fetch_orders_list

orders = fetch_orders_list(
    credential_id="your-credential-id",
    strategy_id="optional-strategy-id"
)

for order in orders:
    print(f"{order['symbol']}: {order['status']}")
```

### Can I modify or cancel orders?

Coming in v0.2.0. Currently, use your broker's platform to modify/cancel.

### Why did my order fail?

Common reasons:
1. **Insufficient Funds**: Not enough balance
2. **Invalid Symbol**: Check symbol format
3. **Market Closed**: Trading hours only
4. **Quantity Issues**: Below minimum or above maximum
5. **Price Limits**: Outside price bands (circuit limits)
6. **Risk Management**: Position limits exceeded

Check the error message in the response:
```python
status, response = place_lt_order(...)
if status != "success":
    print(f"Error: {response.get('message', 'Unknown error')}")
```

### How do I place an options order?

```python
status, response = place_lt_order(
    symbol="NIFTY",
    exchange="NFO",
    quantity=1,
    lot_size=50,  # Nifty lot size
    transaction_type="BUY",
    order_type="MARKET",
    asset_type="OPTIONS",
    option_type="CE",  # or "PE" for put
    strike_price=18000,
    underlying="NIFTY",
    expiry_date="2024-12-26",
    holding_type="INTRADAY",
    credential_id="your-credential-id"
)
```

---

## Backtesting

### How do I backtest a strategy?

```python
from sysstra.sysstra_utils import apply_indicators, calculate_brokerage, generate_mt_report
import pandas as pd

# Fetch historical data
df = pd.DataFrame(fetch_index_candles(...))

# Apply indicators
indicators = {"RSI": {"length": 14}, "EMA": {"length": 20}}
df = apply_indicators(df, indicators)

# Generate signals
df['buy_signal'] = (df['rsi'] < 30) & (df['close'] > df['ema'])
df['sell_signal'] = df['rsi'] > 70

# Simulate trades
trades = []
position = None

for i, row in df.iterrows():
    if row['buy_signal'] and position is None:
        position = {'entry_price': row['close'], 'entry_time': row['timestamp']}
    
    elif row['sell_signal'] and position:
        charges, pnl = calculate_brokerage(
            position['entry_price'], row['close'], 100,
            broker="zerodha", market_type="equity", holding_type="intraday"
        )
        
        trades.append({
            'position_type': 'LONG',
            'investment': 100000,
            'net_pnl': pnl,
            'date': row['timestamp']
        })
        position = None

# Generate report
trades_df = pd.DataFrame(trades)
report = generate_mt_report(trades_df)
print(report)
```

### How accurate is the backtest?

Backtests are approximations. Factors affecting accuracy:
- **Slippage**: Real orders may fill at different prices
- **Order Fill**: Market orders assumed filled at close price
- **Liquidity**: May not be able to trade full quantity
- **Market Impact**: Large orders move prices
- **Brokerage**: Calculated accurately based on broker

For more realistic results:
```python
# Add slippage
actual_fill = entry_price * 1.001  # 0.1% slippage

# Consider bid-ask spread
bid_ask_spread = 0.0005  # 0.05%
buy_price = price * (1 + bid_ask_spread)
sell_price = price * (1 - bid_ask_spread)
```

### Can I backtest options strategies?

Yes, fetch options data and backtest similarly:

```python
option_data = fetch_option_candles(
    underlying="NIFTY",
    start_date=start,
    end_date=end,
    option_type="CE",
    strike_price=18000,
    expiry="current",
    granularity=5
)

df = pd.DataFrame(option_data)
# Apply your strategy logic
```

### How do I optimize strategy parameters?

```python
def backtest_strategy(rsi_length, rsi_buy, rsi_sell):
    # Your backtest logic
    return total_pnl

best_pnl = -float('inf')
best_params = None

for rsi_length in range(10, 20):
    for rsi_buy in range(20, 40, 5):
        for rsi_sell in range(60, 80, 5):
            pnl = backtest_strategy(rsi_length, rsi_buy, rsi_sell)
            
            if pnl > best_pnl:
                best_pnl = pnl
                best_params = (rsi_length, rsi_buy, rsi_sell)

print(f"Best parameters: {best_params}, PnL: {best_pnl}")
```

**Warning**: Beware of overfitting! Use walk-forward analysis and out-of-sample testing.

---

## Performance & Optimization

### Why is my code slow?

Common issues:
1. **Fetching data in loops**: Fetch once, reuse
2. **Too many indicators**: Apply only what you need
3. **Inefficient loops**: Use vectorized pandas operations
4. **Large datasets**: Process in chunks or use smaller granularity

### How can I speed up backtests?

```python
# Bad: Loop through DataFrame
for i, row in df.iterrows():
    df.at[i, 'signal'] = calculate_signal(row)

# Good: Vectorized operations
df['signal'] = (df['rsi'] < 30) & (df['close'] > df['ema'])
```

### How do I handle large datasets?

```python
# Process in chunks
chunk_size = 10000

for chunk in pd.read_csv('large_file.csv', chunksize=chunk_size):
    processed = apply_indicators(chunk, indicators)
    # Process chunk
```

### Should I cache data?

Yes, especially for repeated backtests:

```python
import pickle

# Save data
with open('cached_data.pkl', 'wb') as f:
    pickle.dump(df, f)

# Load data
with open('cached_data.pkl', 'rb') as f:
    df = pickle.load(f)
```

---

## Errors & Troubleshooting

### "API key not set" error

```python
# Make sure you call set_api_key before any data fetching
import sysstra
sysstra.set_api_key("your-api-key")
```

### "Invalid symbol" error

Check symbol format:
- Indian equities: "RELIANCE", "TCS", "INFY"
- Indices: "NIFTY 50" (with space), "NIFTY BANK"
- US equities: "AAPL", "GOOGL", "MSFT"

### "Rate limit exceeded" error

You're making too many requests. Solutions:
```python
import time

# Add delay between requests
for symbol in symbols:
    data = fetch_eod_candles(symbol, ...)
    time.sleep(1)  # 1 second delay
```

Or upgrade your plan for higher rate limits.

### "No data returned" for valid symbol

Check:
1. Date range includes trading days (not weekends/holidays)
2. Symbol format is correct
3. Market was open during that period
4. API key has permissions for that market

### ModuleNotFoundError: No module named 'pandas_ta'

```bash
pip install pandas_ta
```

### ValueError: columns are not unique

Your DataFrame has duplicate column names. Check:
```python
print(df.columns)
# Remove duplicates
df = df.loc[:, ~df.columns.duplicated()]
```

---

## Pricing & Limits

### Is Sysstra free?

Sysstra is available for Enterprise use only.


### What are the rate limits?

| Plan | API Calls/Day | API Calls/Minute | Markets |
|------|---------------|------------------|---------|
| Free | 100 | 10 | NSE only |
| Basic | 10,000 | 100 | NSE, BSE |
| Pro | 100,000 | 500 | All markets |
| Enterprise | Unlimited | Custom | All markets |

### Do I pay broker fees?

Yes, broker fees are separate from Sysstra subscription:
- Zerodha: ₹20 per order (F&O)
- Interactive Brokers: $0.35 min per trade
- See [BROKERS.md](BROKERS.md) for full fee schedules

---

## Still Have Questions?

- **Documentation**: Check our [README](README.md) and [API Reference](API_REFERENCE.md)
- **Examples**: See `/examples` directory for code samples
- **Community**: Join our Discord server (link in README)
- **Support**: Email support@sysstra.com
- **GitHub Issues**: https://github.com/sysstra/sysstra/issues

---

*Last Updated: 2026-05-06*
