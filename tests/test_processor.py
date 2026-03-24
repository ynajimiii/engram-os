import pytest

def test_validate_all_valid():
    result = _validate_all(100, "USD", "1234567890123456")
    assert result["status"] == "success"


def test_validate_all_invalid_amount():
    result = _validate_all(-50, "USD", "1234")
    assert result["status"] == "error"
    assert result["reason"] == "invalid amount"


def test_validate_all_invalid_currency():
    result = _validate_all(200, "JPY", "1234567890123456")
    assert result["status"] == "error"
    assert result["reason"] == "unsupported currency"


def test_validate_all_invalid_card():
    result = _validate_all(300, "USD", "1234")
    assert result["status"] == "error"
    assert result["reason"] == "invalid card"
