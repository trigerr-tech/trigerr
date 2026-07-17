# Technical Indicators Reference

Complete reference for all 40+ technical indicators supported by Sysstra.

---

## Table of Contents

- [Usage](#usage)
- [Trend Indicators](#trend-indicators)
- [Momentum Indicators](#momentum-indicators)
- [Volatility Indicators](#volatility-indicators)
- [Volume Indicators](#volume-indicators)
- [Oscillators](#oscillators)
- [Custom Indicators](#custom-indicators)
- [Multi-Indicator Strategies](#multi-indicator-strategies)

---

## Usage

All indicators are applied using the `apply_indicators()` function:

```python
from sysstra.sysstra_utils import apply_indicators
import pandas as pd

# Your OHLCV DataFrame
df = pd.DataFrame(candles_data)

# Define indicators
indicators = {
    "RSI": {"length": 14},
    "EMA": {"length": 20},
    "MACD": {
        "source": "close",
        "fast_length": 12,
        "slow_length": 26,
        "signal_smoothing": 9
    }
}

# Apply indicators (modifies DataFrame in-place)
df = apply_indicators(df, indicators)
```

**Required DataFrame Columns**: `open`, `high`, `low`, `close`, `volume` (lowercase)

---

## Trend Indicators

### EMA (Exponential Moving Average)

**Description**: Exponential moving average gives more weight to recent prices.

**Parameters**:
```python
{
    "EMA": {
        "length": 20  # Period (default: 20)
    }
}
```

**Output Columns**: `ema`

**Example**:
```python
indicators = {"EMA": {"length": 20}}
df = apply_indicators(df, indicators)

# Generate crossover signals
df['buy_signal'] = (df['close'] > df['ema']) & (df['close'].shift(1) <= df['ema'].shift(1))
```

**Variations**: `EMA5`, `EMA6`, `EMA9`, `EMA14`, `EMA15`, `EMA20`, `EMA50`, `EMA60`, `EMA200`

---

### SMA (Simple Moving Average)

**Description**: Simple average of closing prices over a period.

**Parameters**:
```python
{
    "SMA": {
        "length": 50  # Period (default: 50)
    }
}
```

**Output Columns**: `sma`

**Variations**: `SMA5`, `SMA9`, `SMA13`, `SMA15`, `SMA20`, `SMA34`, `SMA50`, `SMA200`

---

### DEMA (Double Exponential Moving Average)

**Description**: Uses two EMAs to reduce lag.

**Parameters**:
```python
{
    "DEMA": {
        "source": "close",  # Source column
        "length": 20
    }
}
```

**Output Columns**: `dema`

---

### TEMA (Triple Exponential Moving Average)

**Description**: Uses three EMAs for even less lag.

**Parameters**:
```python
{
    "TEMA": {
        "source": "close",
        "length": 20
    }
}
```

**Output Columns**: `tema`

---

### WMA (Weighted Moving Average)

**Description**: Linear weighted moving average.

**Parameters**:
```python
{
    "WMA": {
        "length": 20
    }
}
```

**Output Columns**: `wma`

**Variations**: `WMA9`, `WMA30`

---

### JMA (Jurik Moving Average)

**Description**: Adaptive moving average with customizable smoothness.

**Parameters**:
```python
{
    "JMA": {
        "length": 20,
        "phase": 0,      # Phase shift (-100 to 100)
        "power": 2,      # Smoothing power
        "source": "close"
    }
}
```

**Output Columns**: `jma`, `jma_c` (color indicator)

---

### SUPERTREND

**Description**: Trend-following indicator based on ATR.

**Parameters**:
```python
{
    "SUPERTREND": {
        "length": 10,      # ATR period
        "multiplier": 3.0  # ATR multiplier
    }
}
```

**Output Columns**: `supertrend`, `supertrend_d` (direction: 1=bullish, -1=bearish)

**Example**:
```python
df['long_signal'] = df['supertrend_d'] == 1
df['short_signal'] = df['supertrend_d'] == -1
```

---

### PSAR (Parabolic SAR)

**Description**: Stop and Reverse indicator for trailing stops.

**Parameters**:
```python
{
    "PSAR": {
        "start": 0.02,      # Initial acceleration factor
        "increment": 0.02,   # AF increment
        "max_value": 0.2     # Maximum AF
    }
}
```

**Output Columns**: `psar_l` (long), `psar_s` (short), `psar_af`, `psar_r` (reverse)

---

## Momentum Indicators

### RSI (Relative Strength Index)

**Description**: Measures momentum on a 0-100 scale.

**Parameters**:
```python
{
    "RSI": {
        "length": 14  # Period (default: 14)
    }
}
```

**Output Columns**: `rsi`

**Example**:
```python
indicators = {"RSI": {"length": 14}}
df = apply_indicators(df, indicators)

# Oversold/Overbought signals
df['oversold'] = df['rsi'] < 30
df['overbought'] = df['rsi'] > 70
```

**Variations**: `RSI2`, `RSI10`, `RSI14`

---

### STOCH (Stochastic Oscillator)

**Description**: Compares closing price to price range over time.

**Parameters**:
```python
{
    "STOCH": {
        "k": 14,       # %K period
        "d": 3,        # %D smoothing
        "smooth": 3    # %K smoothing
    }
}
```

**Output Columns**: `stoch_k`, `stoch_d`

**Example**:
```python
# Crossover signals
df['stoch_buy'] = (df['stoch_k'] > df['stoch_d']) & (df['stoch_k'].shift(1) <= df['stoch_d'].shift(1))
```

---

### STOCHRSI (Stochastic RSI)

**Description**: Stochastic oscillator applied to RSI values.

**Parameters**:
```python
{
    "STOCHRSI": {
        "rsi_source": "close",
        "rsi_length": 14,
        "stochastic_length": 14,
        "k": 3,
        "d": 3
    }
}
```

**Output Columns**: `stochrsi_k`, `stochrsi_d`

---

### MACD (Moving Average Convergence Divergence)

**Description**: Shows relationship between two moving averages.

**Parameters**:
```python
{
    "MACD": {
        "source": "close",
        "fast_length": 12,
        "slow_length": 26,
        "signal_smoothing": 9
    }
}
```

**Output Columns**: `macd`, `macd_h` (histogram), `macd_s` (signal)

**Example**:
```python
# Crossover and histogram signals
df['macd_bullish'] = (df['macd'] > df['macd_s']) & (df['macd_h'] > 0)
df['macd_crossover'] = (df['macd'] > df['macd_s']) & (df['macd'].shift(1) <= df['macd_s'].shift(1))
```

---

### MOM (Momentum)

**Description**: Rate of change over a period.

**Parameters**:
```python
{
    "MOM": {
        "source": "close",
        "length": 10
    }
}
```

**Output Columns**: `mom`

---

### ROC (Rate of Change)

**Description**: Percentage change over a period.

**Parameters**:
```python
{
    "ROC": {
        "source": "close",
        "length": 10
    }
}
```

**Output Columns**: `roc`

---

### AO (Awesome Oscillator)

**Description**: Difference between 5 and 34 period SMAs of midpoint prices.

**Parameters**: None (uses fixed periods)

**Output Columns**: `ao`, `ao_color` ("green" or "red")

---

### WILLR (Williams %R)

**Description**: Momentum indicator similar to Stochastic.

**Parameters**:
```python
{
    "WILLR": {
        "length": 14
    }
}
```

**Output Columns**: `willr` (values: -100 to 0)

---

## Volatility Indicators

### ATR (Average True Range)

**Description**: Measures market volatility.

**Parameters**:
```python
{
    "ATR": {
        "length": 14,
        "mamode": "rma"  # Moving average type
    }
}
```

**Output Columns**: `atr`

**Example**:
```python
# Position sizing based on volatility
df['position_size'] = 10000 / df['atr']  # Risk-based sizing
```

---

### BBAND (Bollinger Bands)

**Description**: Volatility bands around moving average.

**Parameters**:
```python
{
    "BBAND": {
        "source": "close",
        "length": 20,
        "std_dev": 2,
        "basis_ma_type": "sma",
        "offset": 0
    }
}
```

**Output Columns**: `bband_l` (lower), `bband_m` (middle), `bband_u` (upper), `bband_b` (bandwidth), `bband_p` (percent)

**Example**:
```python
# Bollinger squeeze
df['squeeze'] = df['bband_b'] < df['bband_b'].rolling(20).min()

# Price breakout
df['breakout_up'] = df['close'] > df['bband_u']
df['breakout_down'] = df['close'] < df['bband_l']
```

**Variations**: `BBAND5`, `BBAND10`, `BBAND20`, `BBAND22`

---

### BBW (Bollinger Bandwidth)

**Description**: Width of Bollinger Bands, normalized.

**Parameters**:
```python
{
    "BBW": {
        "length": 20,
        "std_dev": 2,
        "source": "close",
        "he_length": 100,  # High extreme length
        "lc_length": 100   # Low compression length
    }
}
```

**Output Columns**: `bbw`

---

### SBBW (Smoothed Bollinger Bandwidth)

**Description**: Smoothed version with slope detection.

**Parameters**:
```python
{
    "SBBW": {
        "length": 20,
        "std_dev": 2,
        "source": "close",
        "ma_type": "sma",
        "ma_length": 5
    }
}
```

**Output Columns**: `sbbw`, `sbbw_slope`

---

### CHAIKIN (Chaikin Volatility)

**Description**: ROC of EMA of High-Low range.

**Parameters**:
```python
{
    "CHAIKIN": {
        "length": 10,
        "roc_length": 10
    }
}
```

**Output Columns**: `chaikin`

---

## Volume Indicators

### VFI (Volume Flow Indicator)

**Description**: Combines price and volume to show money flow.

**Parameters**:
```python
{
    "VFI": {
        "length": 130,
        "coef": 0.2,
        "vcoef": 2.5,
        "signal_length": 5,
        "smooth_vfi": True
    }
}
```

**Output Columns**: `vfi`, `vfi_ma` (signal), `vfi_d` (histogram)

---

### VWAP (Volume Weighted Average Price)

**Description**: Average price weighted by volume.

**Parameters**: None (auto-calculated from daily reset)

**Output Columns**: `vwap`

**Example**:
```python
indicators = {"VWAP": {}}
df = apply_indicators(df, indicators)

# Price relative to VWAP
df['above_vwap'] = df['close'] > df['vwap']
```

---

### EFI (Elder Force Index)

**Description**: Combines price change and volume.

**Parameters**:
```python
{
    "EFI": {
        "length": 13
    }
}
```

**Output Columns**: `efi`

---

### AVGVOL (Average Volume)

**Description**: Simple moving average of volume.

**Parameters**:
```python
{
    "AVGVOL": {
        "length": 20
    }
}
```

**Output Columns**: `avg_vol`

---

### VOSC (Volume Oscillator)

**Description**: Difference between two volume moving averages.

**Parameters**:
```python
{
    "VOSC": {
        "short_length": 5,
        "long_length": 10
    }
}
```

**Output Columns**: `v_osc`

---

### VOLUMESLOPE

**Description**: Slope of volume moving average.

**Parameters**:
```python
{
    "VOLUMESLOPE": {
        "length": 20
    }
}
```

**Output Columns**: `vol_ma`, `vol_slope`

---

### VOLMA (Volume Moving Average)

**Description**: EMA or SMA of volume.

**Parameters**:
```python
{
    "VOLMA": {
        "length": 20,
        "mamode": "ema"  # or "sma"
    }
}
```

**Output Columns**: `volma`

---

## Oscillators

### ADX (Average Directional Index)

**Description**: Measures trend strength.

**Parameters**:
```python
{
    "ADX": {
        "length": 14,
        "lensig": 14
    }
}
```

**Output Columns**: `adx`, `adx_dmp` (DI+), `adx_dmn` (DI-)

**Example**:
```python
# Strong trend detection
df['strong_trend'] = df['adx'] > 25

# Trend direction
df['uptrend'] = (df['adx_dmp'] > df['adx_dmn']) & (df['adx'] > 20)
df['downtrend'] = (df['adx_dmn'] > df['adx_dmp']) & (df['adx'] > 20)
```

---

### DMI (Directional Movement Index)

**Description**: Similar to ADX with custom smoothing.

**Parameters**:
```python
{
    "DMI": {
        "adx_smoothing": 14,
        "di_length": 14
    }
}
```

**Output Columns**: `di_plus`, `di_minus`, `di_adx`

---

### SADX (Smoothed ADX)

**Description**: ADX with additional smoothing.

**Parameters**:
```python
{
    "SADX": {
        "adx_length": 14,
        "di_length": 14,
        "smoothing_length": 5,
        "mamode": "sma"
    }
}
```

**Output Columns**: `adx`, `s_adx`

---

### RVGI (Relative Vigor Index)

**Description**: Measures conviction of a price move.

**Parameters**:
```python
{
    "RVGI": {
        "length": 10
    }
}
```

**Output Columns**: `rvgi`, `rvgi_s` (signal)

---

### FISHER (Fisher Transform)

**Description**: Transforms prices to approximate Gaussian distribution.

**Parameters**:
```python
{
    "FISHER": {
        "length": 9,
        "signal": 1
    }
}
```

**Output Columns**: `fisher_t` (transform), `fisher_s` (signal)

---

### VORTEX

**Description**: Identifies start of trends.

**Parameters**:
```python
{
    "VORTEX": {
        "length": 14
    }
}
```

**Output Columns**: `vtx_p` (positive), `vtx_m` (negative)

---

### SMI (Stochastic Momentum Index)

**Description**: Refined stochastic indicator.

**Parameters**:
```python
{
    "SMI": {
        "source": "close",
        "fast": 5,
        "slow": 20,
        "signal": 5
    }
}
```

**Output Columns**: `smi`, `smi_s` (signal), `smi_o` (oscillator)

---

### DPO (Detrended Price Oscillator)

**Description**: Removes trend to show cycles.

**Parameters**:
```python
{
    "DPO": {
        "length": 20
    }
}
```

**Output Columns**: `dpo`

---

### PPO (Percentage Price Oscillator)

**Description**: MACD in percentage terms.

**Parameters**:
```python
{
    "PPO": {
        "fast_length": 12,
        "slow_length": 26
    }
}
```

**Output Columns**: `ppo`, `ppo_h` (histogram), `ppo_s` (signal)

---

### SQZMOM (Squeeze Momentum)

**Description**: Identifies volatility squeeze and momentum.

**Parameters**:
```python
{
    "SQZMOM": {
        "bb_length": 20,
        "bb_mult": 2.0,
        "kc_length": 20,
        "kc_mult": 1.5,
        "use_true_range": True
    }
}
```

**Output Columns**: `sqzmom`

---

### COPPOCK (Coppock Curve)

**Description**: Long-term momentum indicator.

**Parameters**:
```python
{
    "COPPOCK": {
        "length": 10,
        "fast": 11,
        "slow": 14
    }
}
```

**Output Columns**: `coppock`

---

## Custom Indicators

### SWING

**Description**: Identifies market structure (swing highs/lows).

**Usage**: Use `calculate_swing()` function instead of `apply_indicators()`:

```python
from sysstra.sysstra_utils import calculate_swing

df = calculate_swing(df, swing_setup=2, ignore_last_bar=False)
```

**Output Columns**: `swing` ("UP" or "DOWN"), `swing_change` (boolean)

**Example**:
```python
# Trade swing changes
df['entry_long'] = (df['swing_change'] == True) & (df['swing'] == 'UP')
df['entry_short'] = (df['swing_change'] == True) & (df['swing'] == 'DOWN')
```

---

### YONO (ZigZag)

**Description**: Zigzag indicator for significant price moves.

**Parameters**:
```python
{
    "YONO": {
        "depth": 12,
        "deviation": 5,
        "backstep": 3
    }
}
```

**Output Columns**: `yono`

---

### ORB (Opening Range Breakout)

**Description**: High/low of opening range.

**Parameters**:
```python
{
    "ORB": {
        "start_time": "09:15",  # Market open
        "end_time": "09:30"      # End of opening range
    }
}
```

**Output Columns**: `orb_up`, `orb_down`

---

### CHOPZONE (Chop Zone)

**Description**: Identifies choppy vs trending markets.

**Parameters**:
```python
{
    "CHOPZONE": {
        "periods": 30
    }
}
```

**Output Columns**: `chop_zone_color`

---

### FRACTAL (Williams Fractal)

**Description**: Identifies fractal patterns.

**Parameters**:
```python
{
    "FRACTAL": {
        "length": 2
    }
}
```

**Output Columns**: `fractal_up`, `fractal_down`

---

### RDX (Relative Directional Index)

**Description**: Custom directional indicator.

**Parameters**: None (auto-calculated)

**Output Columns**: `rdx`

---

### BBPS (Bollinger Band Sideways)

**Description**: Detects sideways markets using BB.

**Parameters**:
```python
{
    "BBPS": {
        "bb_length": 20,
        "bb_mult": 2,
        "bbr_len": 20,
        "bbr_std_thresh": 0.2
    }
}
```

**Output Columns**: `bbps_sideways`, `bbps_color`

---

### SHA (Smoothed Heikin Ashi)

**Description**: Smoothed version of Heikin Ashi candles.

**Parameters**:
```python
{
    "SHA": {
        "length": 10
    }
}
```

**Output Columns**: `sha_1`, `sha_2`

---

### TVRSI (TradingView RSI)

**Description**: RSI with moving average and bands.

**Parameters**:
```python
{
    "TVRSI": {
        "rsi_length": 14,
        "source": "close",
        "ma_length": 14,
        "ma_type": "sma",
        "bb_mult": 2
    }
}
```

**Output Columns**: `tv_rsi`, `tv_rsi_ma`

---

### BBWRANGE

**Description**: Normalized Bollinger Bandwidth range.

**Parameters**:
```python
{
    "BBWRANGE": {
        "length": 20,
        "deviation": 2
    }
}
```

**Output Columns**: `bbw_range`

---

### NETVOLUME

**Description**: Net volume (buy volume - sell volume estimate).

**Parameters**: None (auto-calculated)

**Output Columns**: `net_volume`

---

### SLOPE

**Description**: Slope of any price series.

**Parameters**:
```python
{
    "SLOPE": {
        "source": "close"  # or "ema", "sma", etc.
    }
}
```

**Output Columns**: `{source}_slope`

---

### MCGD (McGinley Dynamic)

**Description**: Adaptive moving average that adjusts to market speed.

**Parameters**:
```python
{
    "MCGD": {
        "length": 14
    }
}
```

**Output Columns**: `mcgd`

---

### MAC (Moving Average Channel)

**Description**: Channel based on high/low moving averages.

**Parameters**:
```python
{
    "MAC": {
        "upper_length": 20,
        "lower_length": 20
    }
}
```

**Output Columns**: `mac_u` (upper), `mac_l` (lower)

---

### TAM (Trend Adaptive Moving Average)

**Description**: Adaptive MA that responds to trend changes.

**Parameters**:
```python
{
    "TAM": {
        "ma_type": "ema",
        "src": "close",
        "length": 20,
        "off_sig": 5,
        "off_alma": 0.85
    }
}
```

**Output Columns**: `tam_variant`

---

### MTI (Multiple Timeframe Indicator)

**Description**: Combines BB, ADX, and RSI for market state.

**Parameters**:
```python
{
    "MTI": {
        "bb_length": 20,
        "bb_mult": 2,
        "adx_length": 14,
        "rsi_length": 14
    }
}
```

**Output Columns**: Various (complex indicator)

---

## Multi-Indicator Strategies

### Example 1: Trend Following with Confirmation

```python
indicators = {
    "EMA20": {"length": 20},
    "EMA50": {"length": 50},
    "ADX": {"length": 14, "lensig": 14},
    "RSI": {"length": 14}
}

df = apply_indicators(df, indicators)

# Uptrend: Price > EMA20 > EMA50, ADX > 25, RSI not overbought
df['strong_uptrend'] = (
    (df['close'] > df['ema20']) &
    (df['ema20'] > df['ema50']) &
    (df['adx'] > 25) &
    (df['rsi'] < 70)
)

# Entry on pullback
df['entry_signal'] = (
    df['strong_uptrend'] &
    (df['close'] < df['ema20']) &
    (df['close'].shift(1) >= df['ema20'].shift(1))
)
```

### Example 2: Mean Reversion

```python
indicators = {
    "BBAND": {"source": "close", "length": 20, "std_dev": 2, "basis_ma_type": "sma", "offset": 0},
    "RSI": {"length": 14},
    "BBW": {"length": 20, "std_dev": 2, "source": "close", "he_length": 100, "lc_length": 100}
}

df = apply_indicators(df, indicators)

# Low volatility + oversold
df['mean_revert_buy'] = (
    (df['close'] < df['bband_l']) &
    (df['rsi'] < 30) &
    (df['bbw'] < df['bbw'].rolling(50).quantile(0.25))
)

# Exit at mean
df['mean_revert_exit'] = df['close'] > df['bband_m']
```

### Example 3: Momentum Breakout

```python
indicators = {
    "SUPERTREND": {"length": 10, "multiplier": 3.0},
    "MACD": {"source": "close", "fast_length": 12, "slow_length": 26, "signal_smoothing": 9},
    "AVGVOL": {"length": 20}
}

df = apply_indicators(df, indicators)

# Breakout: Supertrend bullish + MACD crossover + high volume
df['breakout_long'] = (
    (df['supertrend_d'] == 1) &
    (df['supertrend_d'].shift(1) == -1) &  # Just turned bullish
    (df['macd'] > df['macd_s']) &
    (df['volume'] > df['avg_vol'] * 1.5)
)
```

### Example 4: Swing Trading

```python
from sysstra.sysstra_utils import calculate_swing

indicators = {
    "RSI": {"length": 14},
    "VWAP": {}
}

df = apply_indicators(df, indicators)
df = calculate_swing(df, swing_setup=2)

# Swing entries with confirmation
df['swing_long_entry'] = (
    (df['swing_change'] == True) &
    (df['swing'] == 'UP') &
    (df['close'] > df['vwap']) &
    (df['rsi'] > 50) &
    (df['rsi'] < 70)
)

df['swing_long_exit'] = (
    (df['swing_change'] == True) &
    (df['swing'] == 'DOWN')
)
```

---

## Performance Tips

1. **Apply Only Needed Indicators**: Each indicator adds computational overhead
2. **Use Appropriate Lengths**: Longer periods = smoother but more lag
3. **Pre-calculate in Backtests**: Apply indicators once, not in every iteration
4. **Vectorize Operations**: Use pandas operations instead of loops
5. **Cache Results**: Store indicator calculations for reuse

---

## Troubleshooting

### NaN Values
- Most indicators need a warmup period (equal to their length parameter)
- First N rows will be NaN or 0 (filled)
- Use `df.dropna()` or check for sufficient data

### Incorrect Values
- Ensure DataFrame has correct column names (lowercase)
- Check for missing data in OHLCV columns
- Verify timestamp column is datetime type

### Performance Issues
- Reduce number of indicators
- Increase data granularity (fewer rows)
- Use simpler indicators first (SMA before JMA)

---

## Support

For indicator-specific questions or issues:
- Check examples in `/examples` directory
- Review the source code in `sysstra/custom_indicators.py` and `sysstra/sysstra_utils.py`
- Open an issue on GitHub with sample data and configuration
- Contact support@sysstra.com

---

## Contributing

Want to add a new indicator? The library is designed to be extensible:

1. Implement the indicator calculation in `custom_indicators.py`
2. Add the indicator case in `apply_indicators()` function
3. Document parameters and outputs
4. Add usage examples
5. Submit via our development process

---

*Last Updated: 2026-05-06*
