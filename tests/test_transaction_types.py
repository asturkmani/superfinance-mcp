"""Tests for transaction type mapping helpers."""

import pytest
from helpers.transaction_types import (
    map_snaptrade_type,
    get_option_multiplier,
    format_option_symbol,
    detect_short_or_cover
)


def test_map_snaptrade_type():
    """Test that SnapTrade types map to canonical types."""
    assert map_snaptrade_type("BUY") == "buy"
    assert map_snaptrade_type("SELL") == "sell"
    assert map_snaptrade_type("DIVIDEND") == "dividend"
    assert map_snaptrade_type("REI") == "dividend_reinvest"
    assert map_snaptrade_type("CONTRIBUTION") == "deposit"
    assert map_snaptrade_type("DEPOSIT") == "deposit"
    assert map_snaptrade_type("WITHDRAWAL") == "withdrawal"
    assert map_snaptrade_type("FEE") == "fee"
    assert map_snaptrade_type("TAX") == "tax"
    assert map_snaptrade_type("FOREIGNTAX") == "tax"
    assert map_snaptrade_type("OPTIONASSIGNMENT") == "option_assignment"
    assert map_snaptrade_type("OPTIONEXPIRATION") == "option_expiration"
    assert map_snaptrade_type("OPTIONEXERCISE") == "option_exercise"
    assert map_snaptrade_type("SPLIT") == "split"
    assert map_snaptrade_type("MERGER") == "merger"
    assert map_snaptrade_type("SPINOFF") == "spinoff"
    assert map_snaptrade_type("SHORT") == "short"
    assert map_snaptrade_type("COVER") == "cover"


def test_map_snaptrade_type_case_insensitive():
    """Test that mapping is case-insensitive."""
    assert map_snaptrade_type("buy") == "buy"
    assert map_snaptrade_type("Buy") == "buy"
    assert map_snaptrade_type("BUY") == "buy"
    assert map_snaptrade_type("dividend") == "dividend"
    assert map_snaptrade_type("DIVIDEND") == "dividend"


def test_map_snaptrade_type_unknown():
    """Test that unknown types map to 'other'."""
    assert map_snaptrade_type("UNKNOWN_TYPE") == "other"
    assert map_snaptrade_type("") == "other"
    assert map_snaptrade_type(None) == "other"


def test_get_option_multiplier():
    """Test option multiplier calculation."""
    assert get_option_multiplier(is_mini=False) == 100
    assert get_option_multiplier(is_mini=True) == 10
    assert get_option_multiplier() == 100  # Default is standard


def test_format_option_symbol_with_ticker():
    """Test that pre-formatted ticker is used when available."""
    symbol = format_option_symbol(
        underlying="AAPL",
        strike=150.0,
        option_type="CALL",
        expiry="2024-01-19",
        ticker="AAPL 150 C 2024-01-19"
    )
    assert symbol == "AAPL 150 C 2024-01-19"


def test_format_option_symbol_from_components():
    """Test building symbol from components."""
    symbol = format_option_symbol(
        underlying="MSFT",
        strike=300.0,
        option_type="PUT",
        expiry="2024-06-21"
    )
    assert symbol == "MSFT 300 P 2024-06-21"


def test_format_option_symbol_call():
    """Test CALL formatting."""
    symbol = format_option_symbol(
        underlying="TSLA",
        strike=250.50,
        option_type="CALL",
        expiry="2024-03-15"
    )
    assert symbol == "TSLA 250.5 C 2024-03-15"


def test_format_option_symbol_put():
    """Test PUT formatting."""
    symbol = format_option_symbol(
        underlying="GOOGL",
        strike=140.0,
        option_type="PUT",
        expiry="2024-12-20"
    )
    assert symbol == "GOOGL 140 P 2024-12-20"


def test_format_option_symbol_partial_components():
    """Test symbol formatting with missing components."""
    # Just underlying
    symbol = format_option_symbol(underlying="INTC")
    assert symbol == "INTC"
    
    # Underlying + strike
    symbol = format_option_symbol(underlying="AMD", strike=100.0)
    assert symbol == "AMD 100"
    
    # Underlying + strike + type
    symbol = format_option_symbol(underlying="NVDA", strike=500.0, option_type="CALL")
    assert symbol == "NVDA 500 C"


def test_format_option_symbol_unknown_underlying():
    """Test handling of missing underlying."""
    symbol = format_option_symbol(
        underlying=None,
        strike=150.0,
        option_type="CALL",
        expiry="2024-01-19"
    )
    assert symbol == "UNKNOWN 150 C 2024-01-19"


def test_detect_short_or_cover_regular_buy():
    """Test that regular buy with positive quantity stays 'buy'."""
    result = detect_short_or_cover("buy", 10.0, is_option=False)
    assert result == "buy"


def test_detect_short_or_cover_regular_sell():
    """Test that regular sell with positive quantity stays 'sell'."""
    result = detect_short_or_cover("sell", 5.0, is_option=False)
    assert result == "sell"


def test_detect_short_or_cover_short_sale():
    """Test that SELL with negative quantity becomes 'short'."""
    result = detect_short_or_cover("sell", -10.0, is_option=False)
    assert result == "short"


def test_detect_short_or_cover_option_cover():
    """Test that BUY with negative quantity on option becomes 'cover'."""
    result = detect_short_or_cover("buy", -2.0, is_option=True)
    assert result == "cover"


def test_detect_short_or_cover_option_buy():
    """Test that regular buy on option with positive quantity stays 'buy'."""
    result = detect_short_or_cover("buy", 2.0, is_option=True)
    assert result == "buy"


def test_detect_short_or_cover_equity_negative_buy():
    """Test that BUY with negative quantity on equity stays 'buy' (not cover)."""
    # Cover only applies to options
    result = detect_short_or_cover("buy", -5.0, is_option=False)
    assert result == "buy"


def test_detect_short_or_cover_none_quantity():
    """Test handling of None quantity."""
    result = detect_short_or_cover("buy", None, is_option=False)
    assert result == "buy"
    
    result = detect_short_or_cover("sell", None, is_option=True)
    assert result == "sell"


def test_detect_short_or_cover_zero_quantity():
    """Test handling of zero quantity."""
    result = detect_short_or_cover("buy", 0.0, is_option=False)
    assert result == "buy"
    
    result = detect_short_or_cover("sell", 0.0, is_option=True)
    assert result == "sell"
