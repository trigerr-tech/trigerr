""" get_symbol_details reads the reference API, not the all_symbols Mongo collection.

These tests fake the reference lookups, so they verify the field mapping offline —
the live response shape is a separate, network-dependent check.
"""
import pytest

from trigerr import utils
from trigerr.data.reference import strike_difference_from

CASH_RECORD = {"symbol": "KOTAKBANK", "exchange": "XNSE", "market": "IN",
               "lot_size": 1, "tick_size": 0.05, "underlying": "KOTAKBANK"}


@pytest.fixture
def fake_reference(monkeypatch):
    """ Installs canned reference responses; returns the dict of recorded calls. """
    calls = {}

    def _install(record=CASH_RECORD, contracts=()):
        def fake_symbol(symbol=None, exchange=None):
            calls["symbol"] = symbol
            return record

        def fake_expiries(exchange, underlying, instrument_type="OPTIONS", **kwargs):
            calls["expiries"] = (exchange, underlying, instrument_type)
            return list(contracts)

        monkeypatch.setattr(utils, "fetch_symbol", fake_symbol)
        monkeypatch.setattr(utils, "fetch_expiries", fake_expiries)
        return calls

    return _install


def _contract(expiry_date, strikes, lot_size=400):
    return {"expiry_date": expiry_date, "lot_size": lot_size,
            "strikes": [{"strike": s} for s in strikes]}


def test_returns_every_field_the_drivers_read(fake_reference):
    """ All 15 backtest drivers index these five keys straight out of the result. """
    fake_reference()
    details = utils.get_symbol_details(db_cursor=None, symbol="KOTAKBANK")
    for field in ("exchange", "market", "lot_size", "expiry_day", "strike_difference"):
        assert field in details, field
    assert details["exchange"] == "XNSE"
    assert details["market"] == "IN"


def test_needs_no_mongo(fake_reference):
    """ db_cursor is accepted and ignored, so the 26 existing call sites keep working. """
    fake_reference()
    assert utils.get_symbol_details(db_cursor=None, symbol="KOTAKBANK") is not None


def test_keeps_the_cash_lot_for_a_spot_symbol(fake_reference):
    """ A spot backtest must NOT inherit the derivative lot from the options contract:
    that would silently multiply every PnL number by the contract size. """
    fake_reference(contracts=[_contract("2026-09-24", [1900, 2000, 2100], lot_size=400)])
    assert utils.get_symbol_details(db_cursor=None, symbol="KOTAKBANK")["lot_size"] == 1


def test_strike_difference_comes_from_the_nearest_expiry(fake_reference):
    fake_reference(contracts=[_contract("2026-12-31", [1000, 2000, 3000]),
                              _contract("2026-09-24", [1900, 2000, 2100])])
    assert utils.get_symbol_details(db_cursor=None, symbol="KOTAKBANK")["strike_difference"] == 100


def test_strike_difference_is_none_without_contracts(fake_reference):
    fake_reference(contracts=[])
    assert utils.get_symbol_details(db_cursor=None, symbol="KOTAKBANK")["strike_difference"] is None


def test_expiry_day_is_none_and_present(fake_reference):
    """ No source of truth on the reference API, but the key must exist — every driver
    copies it into bt_config unconditionally and would KeyError without it. """
    fake_reference()
    assert utils.get_symbol_details(db_cursor=None, symbol="KOTAKBANK")["expiry_day"] is None


def test_unknown_symbol_returns_none(fake_reference):
    fake_reference(record=None)
    assert utils.get_symbol_details(db_cursor=None, symbol="NOPE") is None


def test_strike_ladder_step_is_modal_not_minimal():
    """ Real ladders are denser near the money; min() would report the tightest local
    step rather than the standard one. """
    contract = _contract("2026-09-24", [22000, 22100, 22150, 22200, 22300, 22400])
    assert strike_difference_from(contract) == 100


def test_strike_ladder_step_needs_two_strikes():
    assert strike_difference_from(_contract("2026-09-24", [22000])) is None
    assert strike_difference_from({"strikes": None}) is None
