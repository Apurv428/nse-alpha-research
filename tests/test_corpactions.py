import pytest

from qr.ingest.corpactions import parse_subject


def test_split_irctc():
    p = parse_subject("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share")
    assert p["action"] == "split" and p["price_factor"] == pytest.approx(0.2)


def test_bonus_infy():
    p = parse_subject("Bonus 1:1")
    assert p["action"] == "bonus" and p["price_factor"] == pytest.approx(0.5)
    assert parse_subject("Bonus 3:1")["price_factor"] == pytest.approx(1 / 4)


def test_rights_left_unadjusted_but_parsed():
    p = parse_subject("Rights 3:16 @ Premium Rs 238/-")
    assert p["action"] == "rights" and (p["a"], p["b"]) == (3, 16) and p["price_factor"] is None


def test_dividend_sum_and_no_factor():
    p = parse_subject("Final Dividend - Rs 5 Per Share And Special Dividend - Rs 2.5 Per Share")
    assert p["action"] == "dividend" and p["cash_inr"] == pytest.approx(7.5) and p["price_factor"] is None
    assert parse_subject("Dividend - Re 1 Per Share")["cash_inr"] == 1.0


def test_demerger_and_other():
    assert parse_subject("Scheme Of Arrangement")["action"] == "demerger"
    assert parse_subject("Annual General Meeting")["action"] == "other"
    assert parse_subject("Face Value Split")["action"] == "split_unparsed"


def test_consolidation_is_factor_above_one():
    p = parse_subject("Face Value Consolidation - From Rs 1/- Per Share To Rs 10/- Per Share")
    assert p["price_factor"] == pytest.approx(10.0)
