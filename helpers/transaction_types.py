"""Transaction type mapping for SnapTrade integration."""

SNAPTRADE_TYPE_MAP = {
    'BUY': 'buy',
    'SELL': 'sell',
    'SHORT': 'short',
    'COVER': 'cover',
    'DIVIDEND': 'dividend',
    'STOCK_DIVIDEND': 'stock_dividend',
    'INTEREST': 'interest',
    'REI': 'dividend_reinvest',
    'CONTRIBUTION': 'deposit',
    'DEPOSIT': 'deposit',
    'WITHDRAWAL': 'withdrawal',
    'TRANSFER': 'transfer',
    'TRANSFERIN': 'transfer_in',
    'TRANSFEROUT': 'transfer_out',
    'FEE': 'fee',
    'FOREIGNTAX': 'tax',
    'TAX': 'tax',
    'ADJ': 'adjustment',
    'JOURNALENTRY': 'adjustment',
    'OPTIONASSIGNMENT': 'option_assignment',
    'OPTIONEXPIRATION': 'option_expiration',
    'OPTIONEXERCISE': 'option_exercise',
    'SPLIT': 'split',
    'MERGER': 'merger',
    'SPINOFF': 'spinoff',
}


def map_snaptrade_type(snaptrade_type: str) -> str:
    """
    Map SnapTrade transaction type to canonical type.
    
    Args:
        snaptrade_type: SnapTrade transaction type (e.g., 'BUY', 'SELL')
        
    Returns:
        Canonical type (e.g., 'buy', 'sell', 'dividend')
    """
    if not snaptrade_type:
        return 'other'
    return SNAPTRADE_TYPE_MAP.get(snaptrade_type.upper(), 'other')


def get_option_multiplier(is_mini: bool = False) -> int:
    """
    Get option contract multiplier.
    
    Args:
        is_mini: Whether this is a mini option contract
        
    Returns:
        Multiplier (100 for standard, 10 for mini)
    """
    return 10 if is_mini else 100


def format_option_symbol(
    underlying: str,
    strike: float = None,
    option_type: str = None,
    expiry: str = None,
    ticker: str = None
) -> str:
    """
    Format an option symbol from components.
    
    Args:
        underlying: Underlying ticker symbol
        strike: Strike price
        option_type: 'CALL' or 'PUT'
        expiry: Expiration date (YYYY-MM-DD)
        ticker: Pre-formatted ticker (if available)
        
    Returns:
        Formatted option symbol (e.g., "AAPL 150 C 2024-01-19")
    """
    # Use pre-formatted ticker if available
    if ticker:
        return ticker
    
    # Build from components
    parts = [underlying or 'UNKNOWN']
    
    if strike is not None:
        # Format strike price without unnecessary decimals
        strike_str = f"{strike:.2f}".rstrip('0').rstrip('.')
        parts.append(strike_str)
    
    if option_type:
        # Convert to single letter
        opt_char = 'C' if option_type.upper() == 'CALL' else 'P'
        parts.append(opt_char)
    
    if expiry:
        parts.append(expiry)
    
    return ' '.join(parts)


def detect_short_or_cover(
    transaction_type: str,
    quantity: float,
    is_option: bool = False
) -> str:
    """
    Detect short sale or cover transactions based on negative quantity.
    
    Args:
        transaction_type: Base transaction type ('buy', 'sell')
        quantity: Transaction quantity (can be negative)
        is_option: Whether this is an option transaction
        
    Returns:
        Adjusted transaction type ('short', 'cover', or original type)
    """
    if quantity is None:
        return transaction_type
    
    # SELL with negative quantity = short sale (sell to open)
    if transaction_type == 'sell' and quantity < 0:
        return 'short'
    
    # BUY with negative quantity on options = cover
    if transaction_type == 'buy' and quantity < 0 and is_option:
        return 'cover'
    
    return transaction_type
