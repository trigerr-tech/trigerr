""" calculate_brokerage for the Indian market: the charge schedule every number below is worked out from.

Statutory charges are the same at every broker; brokerage is the one part that differs. Rates in force from 1 April 2026:
  STT            delivery 0.1% buy and sell; intraday equity 0.025% sell; futures 0.05% sell; options 0.15% of the premium, sell
  Exchange (NSE) equity 0.00307%, futures 0.00183%, options 0.03553% of premium (NSE/FA/73061, from 1 March 2026);
                 BSE equity 0.00375%, futures nil, options 0.0325%
  SEBI           Rs 10 per crore (0.0001%) of turnover
  Stamp duty     on the buy side: delivery 0.015%, intraday equity and options 0.003%, futures 0.002%
  GST            18% on brokerage + exchange charges + SEBI fee (+ DP charges on delivery)
STT and stamp duty on futures/options are rounded to the rupee/paisa as the function does; every total here was added up by
hand from those components, not read back from the function.
"""
import pytest

from trigerr.utils import calculate_brokerage


def charges(broker="zerodha", **kwargs):
    args = dict(market_type="options", holding_type="intraday", exchange="NFO", market="IN", lot_size=25, order_type="MARKET")
    return calculate_brokerage(broker=broker, **{**args, **kwargs})


# ---- options: 44 lots of 25 bought at 90, sold at 100; flat Rs 20 per executed order

def test_nse_options_round_trip():
    # brokerage 40 | SEBI 0.21 (209,000 x 0.0001%) | exchange 74.26 (209,000 x 0.03553%) | STT 165 (110,000 x 0.15%)
    # stamp 2.97 (99,000 x 0.003%) | GST 20.60 (18% of 40 + 0.21 + 74.26)   -> total 303.04
    assert charges(buy_price=90, sell_price=100, quantity=1100) == (303.04, 10696.96)


@pytest.mark.parametrize("exchange", ["NSE", "NFO", "XNSE"])
def test_every_label_for_the_nse_prices_options_at_the_nse_rate(exchange):
    # the strategies place options on "NFO", a plain cash symbol on "NSE": both are NSE
    assert charges(buy_price=90, sell_price=100, quantity=1000, exchange=exchange) == (279.79, 9720.21)
    # brokerage 40 | SEBI 0.19 | exchange 67.51 (190,000 x 0.03553%) | STT 150 | stamp 2.70 | GST 19.39


@pytest.mark.parametrize("exchange", ["BSE", "BFO", "XBSE"])
def test_bse_options_use_the_bse_rate(exchange):
    # exchange 61.75 (190,000 x 0.0325%) -> GST 18.35 -> total 272.99
    assert charges(buy_price=90, sell_price=100, quantity=1000, exchange=exchange) == (272.99, 9727.01)


def test_a_short_position_has_the_same_charges_and_the_opposite_sign_of_gross_pnl():
    # the charges depend on the two prices, not on which came first; gross is (90 - 100) x 1,100 = -11,000
    assert charges(buy_price=90, sell_price=100, quantity=1100, position_type="SHORT") == (303.04, -11303.04)


# ---- futures: one Nifty lot (75) bought at 22,000, sold at 22,100

def test_nse_futures_round_trip():
    # brokerage 40 (the Rs 20 cap; 0.03% of 3,307,500 is 992.25) | SEBI 3.31 | exchange 60.53 (0.00183%) | STT 829 (1,657,500 x 0.05%)
    # stamp 33.00 (1,650,000 x 0.002%) | GST 18.69 (18% of 40 + 3.31 + 60.53)   -> total 984.53
    assert charges(market_type="futures", buy_price=22000, sell_price=22100, quantity=75) == (984.53, 6515.47)


def test_bse_futures_pay_no_exchange_charge():
    # brokerage 18 (0.03% of 60,000) | SEBI 0.06 | exchange 0 | STT 15 | stamp 0.60 | GST 3.25   -> 36.91
    assert charges(market_type="futures", exchange="BFO", buy_price=100, sell_price=100, quantity=300) == (36.91, -36.91)


def test_small_futures_trades_pay_the_percentage_not_the_cap():
    # brokerage 18 (0.03% of 60,000) | SEBI 0.06 | exchange 1.10 | STT 15 | stamp 0.60 | GST 3.45   -> 38.21
    assert charges(market_type="futures", buy_price=100, sell_price=100, quantity=300) == (38.21, -38.21)


# ---- equity

def test_intraday_equity_round_trip():
    # 100 shares bought at 100, sold at 102. brokerage 6.06 (0.03% of 20,200) | SEBI 0.02 | exchange 0.62 (0.00307%)
    # STT 2.55 (10,200 x 0.025%) | stamp 0.30 | GST 1.21   -> 10.76
    assert charges(market_type="equity", exchange="NSE", buy_price=100, sell_price=102, quantity=100) == (10.76, 189.24)


def test_delivery_equity_round_trip():
    # zero brokerage; the DP charge is 15.34 | SEBI 0.02 | exchange 0.62 | STT 20.20 (0.1% of 10,000 and of 10,200)
    # stamp 1.50 (0.015%) | GST 2.88   -> 40.56
    assert charges(market_type="equity", holding_type="delivery", exchange="NSE", buy_price=100, sell_price=102, quantity=100) == (40.56, 159.44)


def test_spot_is_priced_by_the_callers_as_equity():
    assert charges(market_type="equity", exchange="NSE", buy_price=100, sell_price=102, quantity=100) is not None


# ---- what it still refuses (None, the signal tts_fees.has_fee_model reads)

@pytest.mark.parametrize("broker, market", [("zerodha", "US"), ("zerodha", "CRYPTO"), ("someone", "IN"), ("", "IN")])
def test_a_broker_or_market_with_no_schedule_returns_none(broker, market):
    assert charges(broker=broker, market=market, buy_price=90, sell_price=100, quantity=1000) is None
