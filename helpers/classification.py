"""
Self-growing classification system for holdings.

Uses a JSON file that grows over time as new tickers are encountered.
When a ticker isn't in the lookup table, Perplexity classifies it and
we add it to the table for future use.
"""

import os
import json
from pathlib import Path
from typing import Optional
from threading import Lock

import cache
from cache import CACHE_CLASSIFICATION_TTL


# Path to the classifications JSON file
CLASSIFICATIONS_FILE = Path(__file__).parent.parent / "data" / "classifications.json"

# Thread lock for file writes
_file_lock = Lock()

# In-memory cache of the classifications (loaded once)
_classifications_data = None


def _load_classifications() -> dict:
    """Load classifications from JSON file."""
    global _classifications_data

    if _classifications_data is not None:
        return _classifications_data

    if not CLASSIFICATIONS_FILE.exists():
        _classifications_data = {"categories": ["Other"], "tickers": {}}
        return _classifications_data

    try:
        with open(CLASSIFICATIONS_FILE, "r") as f:
            _classifications_data = json.load(f)
        return _classifications_data
    except Exception as e:
        print(f"Error loading classifications: {e}")
        _classifications_data = {"categories": ["Other"], "tickers": {}}
        return _classifications_data


def _save_classifications(data: dict) -> bool:
    """Save classifications to JSON file."""
    global _classifications_data

    with _file_lock:
        try:
            # Ensure directory exists
            CLASSIFICATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)

            with open(CLASSIFICATIONS_FILE, "w") as f:
                json.dump(data, f, indent=2)

            _classifications_data = data
            return True
        except Exception as e:
            print(f"Error saving classifications: {e}")
            return False


def _add_classification(symbol: str, name: str, category: str) -> bool:
    """Add a new classification to the persistent store."""
    data = _load_classifications()

    # Add ticker
    data["tickers"][symbol.upper()] = {"name": name, "category": category}

    # Add category if it's new
    if category not in data.get("categories", []):
        data.setdefault("categories", []).append(category)

    return _save_classifications(data)


def get_known_names() -> list[str]:
    """Get list of all known consolidated names."""
    data = _load_classifications()
    names = set()
    for ticker_data in data.get("tickers", {}).values():
        names.add(ticker_data.get("name", ""))
    return sorted(list(names))


def get_known_categories() -> list[str]:
    """Get list of all known categories."""
    data = _load_classifications()
    return data.get("categories", ["Other"])


def get_cached_classification(symbol: str) -> Optional[dict]:
    """Get classification from Redis cache."""
    key = f"classification:{symbol.upper()}"
    return cache.get_cached(key)


def cache_classification(symbol: str, data: dict) -> bool:
    """Cache a classification result in Redis."""
    key = f"classification:{symbol.upper()}"
    return cache.set_cached(key, data, CACHE_CLASSIFICATION_TTL)


def extract_underlying_symbol(symbol: str) -> str:
    """
    Extract underlying ticker from option symbols.

    Examples:
        "AAPL 250117C00150000" -> "AAPL"
        "MU" -> "MU"
    """
    if not symbol:
        return symbol

    parts = symbol.split()
    if len(parts) > 1:
        return parts[0].upper()

    return symbol.upper()


def classify_with_perplexity(symbol: str, description: str = None) -> Optional[dict]:
    """
    Use Perplexity API to classify an unknown ticker.

    Provides existing names and categories so Perplexity can reuse them
    or create new ones if appropriate.

    Returns: {"name": "...", "category": "..."}
    """
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        return None

    try:
        import httpx

        existing_names = get_known_names()
        existing_categories = get_known_categories()

        # Build the prompt with existing context
        names_sample = ", ".join(existing_names[:30])  # Sample of existing names
        categories_list = ", ".join(existing_categories)

        # Include description if available
        desc_line = f'\nDescription from broker: "{description}"' if description else ""

        prompt = f"""For the stock/asset ticker symbol "{symbol}":{desc_line}

**NAME**: The consolidated name groups different tickers that represent the SAME underlying asset or company.
Examples:
- SLV, PSLV, SIVR all → "Silver" (different silver ETFs)
- GLD, PHYS, IAU all → "Gold" (different gold ETFs)
- GOOG, GOOGL → "Google" (different share classes)
- BRK.A, BRK.B → "Berkshire Hathaway"
- ANTH.PVT (any Anthropic tranche) → "Anthropic"
- SPAX.PVT (any SpaceX series) → "SpaceX"

IMPORTANT for NAME:
- Use a simple, recognizable name (e.g., "Google" not "Alphabet Inc Class A")
- Strip dates, tranche info, series letters from descriptions (e.g., "Anthropic (Dec 2024)" → "Anthropic", "SpaceX Series J" → "SpaceX")
- .PVT suffix indicates private equity - use the company name only, extract from description if needed
- Multiple investment rounds in same company should consolidate to ONE name
- If you can't find info about the ticker, use the description but CLEAN IT UP (remove dates, parentheticals, tranche info)

**CATEGORY**: The investment theme/sector exposure based on the company's CURRENT business model. The goal is to help categorise the company into a theme that is easy to understand and use for portfolio management.
Important: Companies pivot! Use current market data:
- IREN, CIFR, CLSK were pure Bitcoin miners but many now do HPC/AI infrastructure
- MSTR is a Bitcoin treasury company, not enterprise software
- Tesla is primarily automotive/energy, not tech
- Anthropic, xAI, OpenAI → "AI/ML" or "Technology"

EXISTING CATEGORIES (use one if it fits, or suggest a new one):
{categories_list}

EXISTING NAMES (use same name if this ticker is related to one):
{names_sample}

Return ONLY a JSON object:
{{"name": "Consolidated Name", "category": "Category"}}"""

        response = httpx.post(
            "https://api.perplexity.ai/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json={
                "model": "sonar",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a financial data assistant. Return only valid JSON, no markdown or explanation."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "max_tokens": 100,
                "temperature": 0.1
            },
            timeout=10.0
        )

        if response.status_code != 200:
            print(f"Perplexity API error for {symbol}: {response.status_code}")
            return None

        result = response.json()
        content = result.get("choices", [{}])[0].get("message", {}).get("content", "")

        # Clean up response
        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        content = content.strip()

        # Parse JSON
        try:
            data = json.loads(content)
            name = data.get("name", symbol)
            category = data.get("category", "Other")

            return {"name": name, "category": category}
        except json.JSONDecodeError:
            print(f"Failed to parse Perplexity response for {symbol}: {content}")
            return None

    except Exception as e:
        print(f"Perplexity API error for {symbol}: {e}")
        return None


def get_classification(symbol: str, description: str = None) -> dict:
    """
    Get classification (name and category) for a holding.

    Flow:
    1. Check Redis cache
    2. Check local JSON lookup table
    3. Call Perplexity API
    4. Save new classification to JSON file for future use
    5. Fallback to defaults

    Args:
        symbol: The ticker symbol
        description: Optional description (used as fallback name)

    Returns:
        {
            "name": "Consolidated Name",
            "category": "Category",
            "source": "lookup" | "perplexity" | "fallback"
        }
    """
    if not symbol:
        return {
            "name": description or "Unknown",
            "category": "Other",
            "source": "fallback"
        }

    # Normalize symbol and extract underlying from options
    symbol = symbol.upper().strip()
    underlying = extract_underlying_symbol(symbol)

    # 1. Check Redis cache
    cached = get_cached_classification(underlying)
    if cached:
        return cached

    # 2. Check local JSON lookup table
    data = _load_classifications()
    if underlying in data.get("tickers", {}):
        ticker_data = data["tickers"][underlying]
        result = {
            "name": ticker_data.get("name", underlying),
            "category": ticker_data.get("category", "Other"),
            "source": "lookup"
        }
        cache_classification(underlying, result)
        return result

    # 3. Try Perplexity for unknown tickers
    perplexity_result = classify_with_perplexity(underlying, description)
    if perplexity_result:
        result = {
            "name": perplexity_result["name"],
            "category": perplexity_result["category"],
            "source": "perplexity"
        }

        # 4. Save to JSON file for future use
        _add_classification(underlying, result["name"], result["category"])

        # Cache in Redis
        cache_classification(underlying, result)

        print(f"New classification added: {underlying} -> {result['name']} ({result['category']})")
        return result

    # 5. Fallback (only if Perplexity fails completely)
    fallback = {
        "name": description or underlying,
        "category": "Private Equity" if underlying.endswith(".PVT") else "Other",
        "source": "fallback"
    }
    cache_classification(underlying, fallback)
    return fallback


def get_option_display_label(option_data: dict) -> str:
    """
    Generate a display label for an option position.

    Args:
        option_data: Option data dict with underlying, strike_price, option_type, expiration_date, etc.

    Returns:
        Label like "AAPL Jan17 150C" or "MU 85P"
    """
    underlying = option_data.get("underlying", "???")
    strike = option_data.get("strike_price", "")
    opt_type = option_data.get("option_type", "").upper()
    expiration = option_data.get("expiration_date", "")

    # Format strike price
    if strike:
        strike_str = str(int(strike)) if float(strike) == int(strike) else str(strike)
    else:
        strike_str = ""

    type_char = opt_type[0] if opt_type else ""

    # Format expiration date (e.g., "2025-01-17" -> "Jan17")
    exp_str = ""
    if expiration:
        try:
            from datetime import datetime
            if isinstance(expiration, str):
                # Try parsing ISO format
                exp_date = datetime.fromisoformat(expiration.replace("Z", "+00:00"))
            else:
                exp_date = expiration
            exp_str = exp_date.strftime("%b%d").replace(" 0", " ").replace("0", "", 1) if exp_date.day < 10 else exp_date.strftime("%b%d")
            # Clean up: "Jan17" not "Jan 17"
            exp_str = exp_date.strftime("%b") + str(exp_date.day)
        except Exception:
            pass

    # Build label: "AAPL Jan17 150C" or "AAPL 150C" (if no date)
    parts = [underlying]
    if exp_str:
        parts.append(exp_str)
    if strike_str and type_char:
        parts.append(f"{strike_str}{type_char}")
    elif strike_str:
        parts.append(strike_str)

    return " ".join(parts)


# Expose categories for external use
def get_category_options() -> list[str]:
    """Get the current list of valid categories."""
    return get_known_categories()


# For backward compatibility
CATEGORY_OPTIONS = get_known_categories()
