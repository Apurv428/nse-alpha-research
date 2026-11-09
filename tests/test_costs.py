"""Cost model against hand calculations (PRD Day 4 gate: a 2025 futures trade at 0.02% STT and a 2026 one at 0.05%)."""
import datetime as dt

import pytest

from qr.portfolio.costs import load_schedule, trade_cost

CR = 1e7  # Rs 1 crore


def test_futures_sell_2025_stt_0p02_hand_calculation():
    c = trade_cost("stk_future", "sell", CR, dt.date(2025, 6, 2))
    assert c["stt"] == pytest.approx(0.0002 * CR) == pytest.approx(2000.0)
    assert c["exchange"] == pytest.approx(0.0000183 * CR) == pytest.approx(183.0)
    assert c["sebi"] == pytest.approx(10.0)
    assert c["stamp"] == 0.0                                    # buy side only
    assert c["brokerage"] == pytest.approx(1000.0)              # 1 bp
    assert c["gst"] == pytest.approx(0.18 * (1000 + 183 + 10))  # 214.74
    assert c["dp"] == 0.0
    assert c["total"] == pytest.approx(2000 + 183 + 10 + 1000 + 214.74)


def test_futures_sell_2026_stt_0p05_after_april_hike():
    c = trade_cost("stk_future", "sell", CR, dt.date(2026, 6, 2))
    assert c["stt"] == pytest.approx(5000.0)
    assert c["total"] == pytest.approx(5000 + 183 + 10 + 1000 + 214.74)
    # the hike takes effect on 2026-04-01 exactly
    assert trade_cost("stk_future", "sell", CR, dt.date(2026, 3, 31))["stt"] == pytest.approx(2000.0)
    assert trade_cost("stk_future", "sell", CR, dt.date(2026, 4, 1))["stt"] == pytest.approx(5000.0)


def test_futures_stt_history_steps():
    f = lambda d: trade_cost("stk_future", "sell", CR, d)["stt"] / CR
    assert f(dt.date(2022, 12, 30)) == pytest.approx(0.0001)
    assert f(dt.date(2023, 4, 3)) == pytest.approx(0.000125)
    assert f(dt.date(2024, 9, 30)) == pytest.approx(0.000125)
    assert f(dt.date(2024, 10, 1)) == pytest.approx(0.0002)
    assert trade_cost("stk_future", "buy", CR, dt.date(2025, 6, 2))["stt"] == 0.0  # sell side only


def test_futures_buy_has_stamp_but_no_stt():
    c = trade_cost("stk_future", "buy", CR, dt.date(2025, 6, 2))
    assert c["stamp"] == pytest.approx(0.00002 * CR) == pytest.approx(200.0) and c["stt"] == 0.0


def test_delivery_buy_and_sell_match_prd_arithmetic():
    d = dt.date(2025, 6, 2)
    buy, sell = trade_cost("eq_delivery", "buy", CR, d), trade_cost("eq_delivery", "sell", CR, d)
    # STT 10 bp, exchange 0.307 bp, SEBI 0.01 bp, stamp 1.5 bp (buy), brokerage 3 bp, GST 18% of (3 + 0.307 + 0.01) bp
    assert buy["stt"] == pytest.approx(10_000) and buy["stamp"] == pytest.approx(1_500) and sell["stamp"] == 0.0
    assert buy["gst"] == pytest.approx(0.18 * (3_000 + 307 + 10))
    assert buy["total"] / CR * 1e4 == pytest.approx(15.4, abs=0.1)      # PRD: a delivery buy costs about 15.4 bp
    assert (sell["total"] - sell["dp"]) / CR * 1e4 == pytest.approx(13.9, abs=0.1)  # sell about 13.9 bp before the DP charge
    assert sell["dp"] == pytest.approx(15.34) and trade_cost("eq_delivery", "sell", CR, d, n_scrips=10)["dp"] == pytest.approx(153.4)
    assert (buy["total"] + sell["total"] - sell["dp"]) / CR * 1e4 == pytest.approx(29.3, abs=0.2)  # round trip about 29 bp


def test_delivery_stt_before_june_2013_is_higher():
    assert trade_cost("eq_delivery", "buy", CR, dt.date(2013, 5, 31))["stt"] == pytest.approx(12_500)
    assert trade_cost("eq_delivery", "buy", CR, dt.date(2013, 6, 3))["stt"] == pytest.approx(10_000)


def test_futures_roll_cost_about_8bp_at_2026_stt():
    d = dt.date(2026, 7, 1)
    roll = trade_cost("stk_future", "buy", CR, d)["total"] + trade_cost("stk_future", "sell", CR, d)["total"]  # buy near, sell next
    assert roll / CR * 1e4 == pytest.approx(8.0, abs=1.0)  # PRD arithmetic: about 8 bp (STT 5 bp dominates)


def test_brokerage_sensitivity_zero_and_five_bp():
    d = dt.date(2025, 6, 2)
    assert trade_cost("eq_delivery", "buy", CR, d, brokerage_bp=0)["brokerage"] == 0.0
    assert trade_cost("eq_delivery", "buy", CR, d, brokerage_bp=5)["brokerage"] == pytest.approx(5_000)
