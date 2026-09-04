# Parity Audit — sysstra SDK → trigerr package (T3.1)

**Date**: 2026-07-17 · **Auditor tier**: Fable · **Verdict**: ✅ **no gaps — safe to flip**

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
