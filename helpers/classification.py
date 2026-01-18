"""
Redis-based classification system for holdings.

All classifications are stored in Redis:
- Auto-generated (via Perplexity): 7-day TTL, regenerated on miss
- User overrides: Permanent (no TTL)

No local JSON file - everything lives in Redis.
"""

import os
import json
from typing import Optional

import cache
from cache import CACHE_CLASSIFICATION_TTL


# Redis key patterns
KEY_CATEGORIES = "superfinance:categories"
KEY_CLASSIFICATION = "superfinance:classification"  # :symbol
KEY_OVERRIDE = "superfinance:classification:override"  # :symbol


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
            # Seed default categories
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

        # Get override keys
        override_keys = client.keys(f"{KEY_OVERRIDE}:*")
        for key in (override_keys or []):
            data = client.get(key)
            if data:
                try:
                    parsed = json.loads(data) if isinstance(data, str) else data
                    if parsed.get("name"):
                        names.add(parsed["name"])
                except:
                    pass

        # Get auto-generated keys
        classification_keys = client.keys(f"{KEY_CLASSIFICATION}:*")
        for key in (classification_keys or []):
            if ":override:" not in key:
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


def get_override(symbol: str) -> Optional[dict]:
    """Get user override for a symbol."""
    symbol = symbol.upper().strip()
    underlying = extract_underlying_symbol(symbol)
    key = f"{KEY_OVERRIDE}:{underlying}"
    return cache.get_cached(key)


def set_override(symbol: str, name: str, category: str) -> bool:
    """Set user override for a symbol (permanent, no TTL)."""
    symbol = symbol.upper().strip()
    underlying = extract_underlying_symbol(symbol)
    key = f"{KEY_OVERRIDE}:{underlying}"

    client = cache._get_redis_client()
    if not client:
        return False

    try:
        data = json.dumps({
            "name": name,
            "category": category,
            "source": "override"
        })
        client.set(key, data)  # No TTL - permanent

        # Also add category if new
        add_category(category)

        # Clear auto-generated cache so override takes effect
        clear_classification_cache(underlying)

        return True
    except Exception as e:
        print(f"Error setting override: {e}")
        return False


def clear_override(symbol: str) -> bool:
    """Remove user override for a symbol."""
    symbol = symbol.upper().strip()
    underlying = extract_underlying_symbol(symbol)
    key = f"{KEY_OVERRIDE}:{underlying}"
    return cache.delete_cached(key)


def get_cached_classification(symbol: str) -> Optional[dict]:
    """Get auto-generated classification from Redis cache."""
    key = f"{KEY_CLASSIFICATION}:{symbol.upper()}"
    return cache.get_cached(key)


def cache_classification(symbol: str, data: dict) -> bool:
    """Cache an auto-generated classification (with TTL)."""
    key = f"{KEY_CLASSIFICATION}:{symbol.upper()}"
    return cache.set_cached(key, data, CACHE_CLASSIFICATION_TTL)


def clear_classification_cache(symbol: str) -> bool:
    """Clear auto-generated cache for a symbol."""
    symbol = symbol.upper().strip()
    underlying = extract_underlying_symbol(symbol)
    key = f"{KEY_CLASSIFICATION}:{underlying}"
    return cache.delete_cached(key)


def classify_with_perplexity(symbol: str, description: str = None) -> Optional[dict]:
    """
    Use Perplexity API to classify an unknown ticker.
    """
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
- Strip dates, tranche info, series letters from descriptions (e.g., "Anthropic (Dec 2024)" → "Anthropic", "SpaceX Series J" → "SpaceX")
- .PVT suffix indicates private equity - use the company name only, extract from description if needed
- Multiple investment rounds in same company should consolidate to ONE name
- If you can't find info about the ticker, use the description but CLEAN IT UP (remove dates, parentheticals, tranche info)

**CATEGORY**: The investment theme/sector exposure based on the company's CURRENT business model.
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

    Priority:
    1. User override (permanent in Redis)
    2. Auto-generated cache (7-day TTL in Redis)
    3. Perplexity API (generates and caches)
    4. Fallback defaults
    """
    if not symbol:
        return {
            "name": description or "Unknown",
            "category": "Other",
            "source": "fallback"
        }

    symbol = symbol.upper().strip()
    underlying = extract_underlying_symbol(symbol)

    # 1. Check user override (permanent)
    override = get_override(underlying)
    if override:
        return override

    # 2. Check auto-generated cache
    cached = get_cached_classification(underlying)
    if cached:
        return cached

    # 3. Try Perplexity for unknown tickers
    perplexity_result = classify_with_perplexity(underlying, description)
    if perplexity_result:
        result = {
            "name": perplexity_result["name"],
            "category": perplexity_result["category"],
            "source": "perplexity"
        }

        # Add category if new
        add_category(result["category"])

        # Cache in Redis (with TTL)
        cache_classification(underlying, result)

        print(f"New classification: {underlying} -> {result['name']} ({result['category']})")
        return result

    # 4. Fallback
    fallback = {
        "name": description or underlying,
        "category": "Private Equity" if underlying.endswith(".PVT") else "Other",
        "source": "fallback"
    }
    cache_classification(underlying, fallback)
    return fallback


def update_classification(symbol: str, name: Optional[str] = None, category: Optional[str] = None) -> dict:
    """
    Update/override the classification for a symbol.
    Stores as permanent override in Redis.
    """
    symbol = symbol.upper().strip()
    underlying = extract_underlying_symbol(symbol)

    # Get existing (from override or cache)
    existing = get_override(underlying) or get_cached_classification(underlying) or {}

    new_name = name if name is not None else existing.get("name", underlying)
    new_category = category if category is not None else existing.get("category", "Other")

    if set_override(underlying, new_name, new_category):
        return {
            "success": True,
            "symbol": underlying,
            "name": new_name,
            "category": new_category
        }
    else:
        return {"success": False, "error": "Failed to save override"}


def get_all_classifications() -> dict:
    """Get all classifications from Redis."""
    client = cache._get_redis_client()
    if not client:
        return {"categories": DEFAULT_CATEGORIES, "tickers": {}}

    tickers = {}

    try:
        # Get overrides first (they take priority)
        override_keys = client.keys(f"{KEY_OVERRIDE}:*")
        for key in (override_keys or []):
            symbol = key.split(":")[-1]
            data = client.get(key)
            if data:
                try:
                    parsed = json.loads(data) if isinstance(data, str) else data
                    tickers[symbol] = {
                        "name": parsed.get("name", symbol),
                        "category": parsed.get("category", "Other"),
                        "source": "override"
                    }
                except:
                    pass

        # Get auto-generated (don't overwrite overrides)
        classification_keys = client.keys(f"{KEY_CLASSIFICATION}:*")
        for key in (classification_keys or []):
            if ":override:" not in key:
                symbol = key.split(":")[-1]
                if symbol not in tickers:  # Don't overwrite overrides
                    data = client.get(key)
                    if data:
                        try:
                            parsed = json.loads(data) if isinstance(data, str) else data
                            tickers[symbol] = {
                                "name": parsed.get("name", symbol),
                                "category": parsed.get("category", "Other"),
                                "source": parsed.get("source", "perplexity")
                            }
                        except:
                            pass

        categories = get_known_categories()
        return {"categories": categories, "tickers": tickers}

    except Exception as e:
        print(f"Error getting all classifications: {e}")
        return {"categories": DEFAULT_CATEGORIES, "tickers": {}}


def get_option_display_label(option_data: dict) -> str:
    """Generate a display label for an option position."""
    underlying = option_data.get("underlying", "???")
    strike = option_data.get("strike_price", "")
    opt_type = option_data.get("option_type", "").upper()
    expiration = option_data.get("expiration_date", "")

    if strike:
        strike_str = str(int(strike)) if float(strike) == int(strike) else str(strike)
    else:
        strike_str = ""

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
        except Exception:
            pass

    parts = [underlying]
    if exp_str:
        parts.append(exp_str)
    if strike_str and type_char:
        parts.append(f"{strike_str}{type_char}")
    elif strike_str:
        parts.append(strike_str)

    return " ".join(parts)


# Expose for backward compatibility
def get_category_options() -> list[str]:
    return get_known_categories()

CATEGORY_OPTIONS = DEFAULT_CATEGORIES
