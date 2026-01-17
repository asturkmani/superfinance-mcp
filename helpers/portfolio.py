"""Portfolio helpers for loading and saving manual portfolios."""

import json
import os
import uuid


# Portfolio file location - configurable via environment variable
PORTFOLIO_FILE = os.getenv(
    "SUPERFINANCE_PORTFOLIO_FILE",
    os.path.expanduser("~/.superfinance/portfolios.json")
)


def load_portfolios() -> dict:
    """Load portfolios from JSON file."""
    try:
        if os.path.exists(PORTFOLIO_FILE):
            with open(PORTFOLIO_FILE, "r") as f:
                return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Could not load portfolios: {e}")
    return {"portfolios": {}}


def save_portfolios(data: dict) -> None:
    """Save portfolios to JSON file."""
    # Ensure directory exists
    os.makedirs(os.path.dirname(PORTFOLIO_FILE), exist_ok=True)
    with open(PORTFOLIO_FILE, "w") as f:
        json.dump(data, f, indent=2)


def generate_position_id() -> str:
    """Generate a unique position ID."""
    return str(uuid.uuid4())[:8]
