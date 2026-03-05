"""
Redis-based classification system for holdings.

Simple model:
1. First lookup → Perplexity classifies → stored permanently in Redis
2. User override → updates same entry in Redis

All classifications are permanent (no TTL).
Uses locking to prevent duplicate Perplexity calls for the same symbol.
"""

import os
import json
import threading
import time
from typing import Optional

import cache


# Redis key patterns
KEY_CATEGORIES = "superfinance:categories"
KEY_CLASSIFICATION = "superfinance:classification"  # :{symbol}

# Lock to prevent concurrent Perplexity calls for the same symbol
_classification_lock = threading.Lock()
_in_flight: set[str] = set()  # Symbols currently being classified


# Default categories (seeded on first use)
DEFAULT_CATEGORIES = [
    "Technology",
    "Memory",
    "Commodities",
    "Energy",
    "Crypto/Blockchain",
    "Healthcare",
    "Finance",
    "Private Equity",
    "Real Estate",
    "Consumer",
    "Industrial",
    "Utilities",
    "Telecom",
    "Other"
]


def _ensure_categories() -> list[str]:
    """Ensure categories exist in Redis, seed defaults if empty."""
    client = cache._get_redis_client()
    if not client:
        return DEFAULT_CATEGORIES

    try:
        categories = client.smembers(KEY_CATEGORIES)
        if not categories:
            for cat in DEFAULT_CATEGORIES:
                client.sadd(KEY_CATEGORIES, cat)
            return DEFAULT_CATEGORIES
        return sorted(list(categories))
    except Exception as e:
        print(f"Error loading categories: {e}")
        return DEFAULT_CATEGORIES


def get_known_categories() -> list[str]:
    """Get list of all known categories."""
    return _ensure_categories()


def add_category(category: str) -> bool:
    """Add a new category."""
    client = cache._get_redis_client()
    if not client:
        return False

    try:
        client.sadd(KEY_CATEGORIES, category)
        return True
    except Exception as e:
        print(f"Error adding category: {e}")
        return False


def get_known_names() -> list[str]:
    """Get list of all known consolidated names from Redis."""
    client = cache._get_redis_client()
    if not client:
        return []

    try:
        names = set()
        keys = client.keys(f"{KEY_CLASSIFICATION}:*")
        for key in (keys or []):
            data = client.get(key)
            if data:
                try:
                    parsed = json.loads(data) if isinstance(data, str) else data
                    if parsed.get("name"):
                        names.add(parsed["name"])
                except:
                    pass
        return sorted(list(names))
    except Exception as e:
        print(f"Error getting names: {e}")
        return []


def extract_underlying_symbol(symbol: str) -> str:
    """Extract underlying ticker from option symbols."""
    if not symbol:
        return symbol
    parts = symbol.split()
    if len(parts) > 1:
        return parts[0].upper()
    return symbol.upper()


def get_stored_classification(symbol: str) -> Optional[dict]:
    """Get classification from Redis."""
    symbol = symbol.upper().strip()
    underlying = extract_underlying_symbol(symbol)
    key = f"{KEY_CLASSIFICATION}:{underlying}"

    # Use client directly since we store with full key (not via cache helper)
    client = cache._get_redis_client()
    if not client:
        return None

    try:
        data = client.get(key)
        if data:
            return json.loads(data) if isinstance(data, str) else data
        return None
    except Exception as e:
        print(f"Error getting classification for {symbol}: {e}")
        return None


def store_classification(symbol: str, name: str, category: str, source: str = "perplexity") -> bool:
    """Store classification in Redis (permanent, no TTL)."""
    symbol = symbol.upper().strip()
    underlying = extract_underlying_symbol(symbol)
    key = f"{KEY_CLASSIFICATION}:{underlying}"

    client = cache._get_redis_client()
    if not client:
        return False

    try:
        data = json.dumps({
            "name": name,
            "category": category,
            "source": source
        })
        client.set(key, data)  # No TTL - permanent
        add_category(category)
        return True
    except Exception as e:
        print(f"Error storing classification: {e}")
        return False


def delete_classification(symbol: str) -> bool:
    """Delete classification from Redis."""
    symbol = symbol.upper().strip()
    underlying = extract_underlying_symbol(symbol)
    key = f"{KEY_CLASSIFICATION}:{underlying}"

    client = cache._get_redis_client()
    if not client:
        return False

    try:
        client.delete(key)
        return True
    except Exception as e:
        print(f"Error deleting classification for {symbol}: {e}")
        return False


def classify_with_perplexity(symbol: str, description: str = None) -> Optional[dict]:
    """Use Perplexity API to classify an unknown ticker."""
    api_key = os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        return None

    try:
        import httpx

        existing_names = get_known_names()
        existing_categories = get_known_categories()

        names_sample = ", ".join(existing_names[:30])
        categories_list = ", ".join(existing_categories)

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
- Strip dates, tranche info, series letters from descriptions
- .PVT suffix indicates private equity - use the company name only
- If you can't find info, clean up the description (remove dates, parentheticals)

**CATEGORY**: The investment theme/sector based on CURRENT business model.
Important: Companies pivot!
- IREN, CIFR, CLSK were Bitcoin miners but many now do HPC/AI
- MSTR is a Bitcoin treasury company
- Anthropic, xAI, OpenAI → "Technology" or "AI/ML"

EXISTING CATEGORIES (use one if it fits, or suggest a new one):
{categories_list}

EXISTING NAMES (use same name if this ticker is related):
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
                    {"role": "system", "content": "You are a financial data assistant. Return only valid JSON."},
                    {"role": "user", "content": prompt}
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

        content = content.strip()
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])
        content = content.strip()

        try:
            data = json.loads(content)
            return {"name": data.get("name", symbol), "category": data.get("category", "Other")}
        except json.JSONDecodeError:
            print(f"Failed to parse Perplexity response for {symbol}: {content}")
            return None

    except Exception as e:
        print(f"Perplexity API error for {symbol}: {e}")
        return None


def get_classification(symbol: str, description: str = None) -> dict:
    """
    Get classification for a holding.

    1. Check Redis (permanent storage)
    2. If in-flight by another thread, wait for it
    3. If not found, call Perplexity and store permanently
    4. Fallback if Perplexity fails

    Uses locking to prevent duplicate Perplexity calls for the same symbol.
    """
    if not symbol:
        return {"name": description or "Unknown", "category": "Other", "source": "fallback"}

    symbol = symbol.upper().strip()
    underlying = extract_underlying_symbol(symbol)

    # 1. Quick check Redis (no lock needed for read)
    stored = get_stored_classification(underlying)
    if stored:
        return stored

    # 2. Acquire lock to check/update in-flight status
    should_classify = False
    with _classification_lock:
        # Re-check cache (might have been populated while waiting for lock)
        stored = get_stored_classification(underlying)
        if stored:
            return stored

        if underlying in _in_flight:
            # Another thread is working on it
            should_classify = False
        else:
            # We'll do the classification
            _in_flight.add(underlying)
            should_classify = True

    # 3. If another thread is classifying, wait for result
    if not should_classify:
        for _ in range(30):  # Max 15 seconds
            time.sleep(0.5)
            stored = get_stored_classification(underlying)
            if stored:
                return stored
            with _classification_lock:
                if underlying not in _in_flight:
                    # Other thread finished, check cache
                    stored = get_stored_classification(underlying)
                    if stored:
                        return stored
                    break
        # Timeout or other thread failed - return fallback
        fallback_name = description or underlying
        fallback_category = "Private Equity" if underlying.endswith(".PVT") else "Other"
        return {"name": fallback_name, "category": fallback_category, "source": "fallback"}

    # 4. We own it - do the classification
    try:
        perplexity_result = classify_with_perplexity(underlying, description)
        if perplexity_result:
            store_classification(underlying, perplexity_result["name"], perplexity_result["category"], "perplexity")
            print(f"Classified: {underlying} → {perplexity_result['name']} ({perplexity_result['category']})")
            return {"name": perplexity_result["name"], "category": perplexity_result["category"], "source": "perplexity"}

        # Fallback if Perplexity fails
        fallback_name = description or underlying
        fallback_category = "Private Equity" if underlying.endswith(".PVT") else "Other"
        store_classification(underlying, fallback_name, fallback_category, "fallback")
        return {"name": fallback_name, "category": fallback_category, "source": "fallback"}
    finally:
        with _classification_lock:
            _in_flight.discard(underlying)


def update_classification(symbol: str, name: Optional[str] = None, category: Optional[str] = None) -> dict:
    """
    Update classification for a symbol. Just overwrites the entry in Redis.
    """
    symbol = symbol.upper().strip()
    underlying = extract_underlying_symbol(symbol)

    # Get existing
    existing = get_stored_classification(underlying) or {}

    new_name = name if name is not None else existing.get("name", underlying)
    new_category = category if category is not None else existing.get("category", "Other")

    if store_classification(underlying, new_name, new_category, "override"):
        return {"success": True, "symbol": underlying, "name": new_name, "category": new_category}
    else:
        return {"success": False, "error": "Failed to save classification"}


def get_all_classifications() -> dict:
    """Get all classifications from Redis."""
    client = cache._get_redis_client()
    if not client:
        return {"categories": DEFAULT_CATEGORIES, "tickers": {}}

    tickers = {}
    try:
        keys = client.keys(f"{KEY_CLASSIFICATION}:*")
        for key in (keys or []):
            symbol = key.split(":")[-1]
            data = client.get(key)
            if data:
                try:
                    parsed = json.loads(data) if isinstance(data, str) else data
                    tickers[symbol] = {
                        "name": parsed.get("name", symbol),
                        "category": parsed.get("category", "Other"),
                        "source": parsed.get("source", "unknown")
                    }
                except:
                    pass

        return {"categories": get_known_categories(), "tickers": tickers}
    except Exception as e:
        print(f"Error getting classifications: {e}")
        return {"categories": DEFAULT_CATEGORIES, "tickers": {}}


def get_option_display_label(option_data: dict) -> str:
    """Generate a display label for an option position."""
    underlying = option_data.get("underlying", "???")
    strike = option_data.get("strike_price", "")
    opt_type = option_data.get("option_type", "").upper()
    expiration = option_data.get("expiration_date", "")

    strike_str = str(int(strike)) if strike and float(strike) == int(strike) else str(strike) if strike else ""
    type_char = opt_type[0] if opt_type else ""

    exp_str = ""
    if expiration:
        try:
            from datetime import datetime
            if isinstance(expiration, str):
                exp_date = datetime.fromisoformat(expiration.replace("Z", "+00:00"))
            else:
                exp_date = expiration
            exp_str = exp_date.strftime("%b") + str(exp_date.day)
        except:
            pass

    parts = [underlying]
    if exp_str:
        parts.append(exp_str)
    if strike_str and type_char:
        parts.append(f"{strike_str}{type_char}")
    elif strike_str:
        parts.append(strike_str)

    return " ".join(parts)


# Backward compatibility
def get_category_options() -> list[str]:
    return get_known_categories()

CATEGORY_OPTIONS = DEFAULT_CATEGORIES
