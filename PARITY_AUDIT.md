# Parity Audit — sysstra SDK → trigerr package (T3.1)

> ⚠️ **SUPERSEDED — this audit describes 2026-07-17 and its verdict no longer holds.**
> It was written the day trigerr was imported and predates every subsequent sysstra commit.
> Re-audited 2026-09-07; the drift found is recorded in "2026-09-07 re-audit" below. Do not
> cite the "no gaps" verdict or the `__version__ = "0.1.0"` line — both are stale.

**Date**: 2026-07-17 · **Auditor tier**: Fable · **Verdict (as of that date only)**: ✅ **no gaps — safe to flip**

Answers one question before T3.3 flips imports: *does the `trigerr` package provide every
symbol the consumer repos actually pull from the legacy `sysstra` package, with identical
signatures?* A missed symbol behind a `*`-import is a runtime `NameError` in a live strategy,
so this was checked mechanically, not by eyeball.

## Scope — the complete `sysstra` import surface

Repo-wide grep over `trigerr-trading-engine` and `trigerr-oms` confirms **exactly 4 files**
import `sysstra` (11 import lines total) — no strategy file imports it directly (they get
symbols via `from sts_common import *`), and no dynamic-dispatch pattern (`getattr`/
`globals()[...]`/`importlib`) pulls SDK names by string anywhere in either repo.

| Consumer | Imports |
|---|---|
| `trigerr-trading-engine/sts_common.py` | `import sysstra` (for `set_api_key`/`set_data_url`/`set_orders_url`) + `from sysstra.sysstra_utils import *` + `from sysstra.orders import *` + `from sysstra.data import *` |
| `trigerr-trading-engine/tests/sdk_registry.py` | named imports from `orders.virtual`, `orders.live`, `orders.orders_utils`, `data.live`, `sysstra_utils` |
| `trigerr-trading-engine/tests/sims/sim_stubs.py` | `orders.orders_utils.check_open_orders` (aliased) |
| `trigerr-oms/sos_common.py` | `sysstra_utils.calculate_brokerage` |

## Method

1. **Export surfaces** (AST): none of the consumer-facing modules define `__all__`
   (`__all__` exists only inside `ta/`, mirrored identically on both sides), so a `*`-import
   binds every non-underscore module-level name **including names the module itself imports**.
   Surfaces were computed accordingly for `sysstra_utils`/`utils`, all 4 `orders/` submodules,
   both `data/` submodules, `__init__` and `config` — on both packages.
2. **Usage scan** (AST): every identifier loaded (names + attribute accesses) across **all**
   engine `.py` files (strategies, celery, runner, tests, sims) + `sos_common.py`, intersected
   with the star surfaces; union with the explicitly imported names.
3. **Signature comparison**: positional/keyword args and default values compared node-by-node
   for every required symbol.
4. **Body equivalence**: namespace-normalized (`sysstra`→`trigerr`) file diff of the entire
   package, to catch same-name-different-behavior drift.
5. **Import smoke test**: `import trigerr(.utils/.orders/.data/.config)` + the `set_*` trio
   executed in a clean venv (deps: numpy, pandas, requests, redis, pymongo, numba, tqdm).

## Result: 79 required symbols, all present, all signature-identical

| sysstra home | trigerr home | Required symbols (used by consumers) |
|---|---|---|
| `sysstra.sysstra_utils` | `trigerr.utils` | `apply_indicators`, `calculate_brokerage`, `calculate_entry_quantity`, `calculate_exit_quantity`, `calculate_funds`, `calculate_liquidation_price`, `calculate_swing`, `change_granularity`, `convert_candle_pattern`, `fetch_available_funds`, `find_last_trading_date`, `find_nearest_strike_price`, `get_bar_color`, `merge_candle`, `nearest_expiry_option_data`, `round_strike_price`, `round_to_tick_multiple` |
| `sysstra.orders.orders_utils` | `trigerr.orders.orders_utils` | `add_order_to_redis`, `calculate_brokerage` (re-export), `check_existing_order`, `check_open_orders`, `convert_to_trades`, `fetch_last_order`, `fetch_orders_list`, `fetch_orders_mgdb` |
| `sysstra.orders.live` | `trigerr.orders.live` | `check_order_status`, `modify_live_order`, `place_lt_order`, `poll_order_status`, `save_lt_order`, `save_lt_trade` |
| `sysstra.orders.virtual` | `trigerr.orders.virtual` | `place_vt_order`, `save_vt_trade` |
| `sysstra.orders.backtest` | `trigerr.orders.backtest` | `place_bt_order` |
| `sysstra.data.historical` | `trigerr.data.historical` | `fetch_eod_candles`, `fetch_futures_candle`, `fetch_index_candles`, `fetch_option_candles_by_symbol` |
| `sysstra.data.live` | `trigerr.data.live` | `fetch_current_day_open`, `fetch_live_candle`, `fetch_live_candles`, `fetch_live_option_candle`, `fetch_live_option_candles`, `fetch_recent_candle` |
| `sysstra` (top-level) | `trigerr` | `set_api_key`, `set_data_url`, `set_orders_url` |

Stdlib/third-party names (`json`, `requests`, `datetime`, `math`, `time`, `tb`, `ObjectId`)
and module vars (`config`, `data_url`, `orders_url`) also ride the star surfaces; they are
imported identically in the trigerr modules, so they carry over with zero risk.

**Gap list: empty.** Full module surfaces (not just used names) are also identical pair-by-pair.

## Deliberate divergences found (all sound — keep)

1. **`trigerr/config.py` defaults `orders_url`/`data_url` to `None`** where sysstra hardcodes
   its production API URLs. Safer for white-label: a consumer that forgets
   `set_data_url()` fails loudly instead of silently hitting sysstra production.
   `sts_common.py` always calls the `set_*` trio from platform config, so engine behavior
   is unchanged.
2. `trigerr/__init__.py` adds `__version__ = "0.1.0"`.
3. `trigerr/orders/orders_utils.py` imports from `trigerr.utils` (rename correctly applied).
4. Remaining diffs are whitespace/trailing-newline only.

## Findings for T3.2 (cosmetic — nothing blocks T3.3)

1. **`trigerr/custom_indicators.py::jurik_moving_average` (lines 456–486)** uses a temp
   DataFrame column literally named `'sysstra'`. Internally consistent (all 3 occurrences
   match) and no engine code reads that column string — zero functional risk, but it's a
   brand leak; rename the column (e.g. `'jma_src'`) in T3.2.
2. **Namespace quirk** (inherited from sysstra, do not "fix" casually): `from .config import
   config` in `__init__.py` makes `trigerr.config` resolve to the config **dict**, shadowing
   the `trigerr.config` submodule after `import trigerr`. Consumers only use the `set_*`
   wrappers, so this is inert — just don't write new code that expects `trigerr.config` to be
   a module.
3. Noted in passing (engine-side, inherited, out of SDK scope): strategies `eval()` numeric
   strategy params from Mongo-sourced dicts (e.g. `syss_test.py:543`). Pre-existing pattern —
   flagged for a later hardening pass, not touched.

## T3.3 flip map (exact rewrites)

| File | From | To |
|---|---|---|
| `sts_common.py:2-9` | `import sysstra` / `sysstra.set_*` / `from sysstra.sysstra_utils import *` / `from sysstra.orders import *` / `from sysstra.data import *` | `import trigerr` / `trigerr.set_*` / `from trigerr.utils import *` / `from trigerr.orders import *` / `from trigerr.data import *` |
| `tests/sdk_registry.py:5-9` | `from sysstra.<sub> import <names>` | `from trigerr.<sub> import <names>` (module paths unchanged; `sysstra_utils`→`utils`) |
| `tests/sims/sim_stubs.py:23` | `from sysstra.orders.orders_utils import check_open_orders as ...` | `from trigerr.orders.orders_utils import ...` |
| `trigerr-oms/sos_common.py:9` | `from sysstra.sysstra_utils import calculate_brokerage` | `from trigerr.utils import calculate_brokerage` |

Plus: config key `sysstra_api_key` → `trigerr_api_key` in `sts_config.py` + seed files
(loader reads new key, falls back to old for one release), and `pip install -e <trigerr repo>`
wherever the engine/OMS venvs are built.

---

## 2026-09-07 re-audit

**Verdict**: ❌ **trigerr was four sysstra commits behind.** The 2026-07-17 audit compared the
two packages on the day trigerr was imported; sysstra moved on and nothing propagated. The data
layer has since been migrated (see below); the rest is still open.

### Closed by the data-services migration (2026-09-07)

- `7a2c28b` / `37eea38` (2026-08-20/21) — sysstra replaced raw `requests.post` against
  sysstra-data-api's `/fetch-*` routes with the `sysstra_data` client against
  sysstra-data-services' `/market-data/*`. trigerr has now done the same, including the
  `timeout=300` that the EOD cold-cache-stampede incident of 2026-08-21 prompted.
- `6084dbb` — `fetch_pre_open_candles` was missing entirely; added.
- `d1f2766` — `fetch_futures_candle` was missing `expiry="current"`; added last in the
  signature so no positional caller breaks.
- `fetch_option_candles_by_symbol` / `_by_date` / `fetch_option_candle_by_timestamp` have no
  successor route on data-services and now raise `NotImplementedError` rather than 404-ing into
  a swallowed `[]`. Verified zero call sites across project-trigerr.

### Still open

- **`e96e241` — structured logging.** sysstra replaced `print()` with `_log()` across 8 modules;
  trigerr still has ~115 prints in the data/indicator/order paths and wires `trigerr_logging`
  only for correlation IDs. Some `except: print(); pass` blocks also became
  `except: _log().exception(); return dataframe`, so a few indicator functions have **different
  fall-through return values** in the two packages.
- **`tam_variant` has forked, and it is not just a signature.** trigerr
  (`custom_indicators.py`) returns a single MA Series selected by `ma_type`; sysstra dropped that
  ladder and returns the **DataFrame** with new `adx` and `dmi_matrix` columns, plus `atr_len` /
  `adx_smoothing` parameters. The rewrite arrived inside `e96e241`, whose message mentions only
  logging. Any strategy relying on either shape is not portable between the packages.
- **Latent bug in trigerr's surviving `tam_variant`**: a misplaced paren makes `v8` a tuple, so
  `ma_type="HullMA"` returns a tuple rather than a Series.
- **`data/live.py` wire-format fork.** trigerr's `fetch_live_future_candle` unwraps
  `json.loads(poc_result)[key_name]`, sysstra's does not (commit `64cd162`). The two packages
  now expect structurally different Redis payloads and are **not interchangeable against a
  shared Redis**. trigerr's version is paired with a matching change in
  `trigerr-data-collection-in`.

### Divergences from the original list that are now wrong

Item 1 below ("defaults `orders_url`/`data_url` to `None` … fails loudly") is only half true:
`data_url` unset does **not** fail loudly — the fetch raises inside a bare `except` and returns
`[]`, so a sweep completes and writes an empty report. That is what
`trigerr-backtesting-strategies` hit. Item 2's `__version__ = "0.1.0"` is stale; the package is
at 0.5.0.
