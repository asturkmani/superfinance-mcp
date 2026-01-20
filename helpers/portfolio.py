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


def generate_liability_id() -> str:
    """Generate a unique liability ID with liab_ prefix."""
    return f"liab_{str(uuid.uuid4())[:8]}"


# =========================================================================
# Liability Functions
# =========================================================================

def load_liabilities() -> list[dict]:
    """Load all liabilities from the portfolios file."""
    try:
        data = load_portfolios()
        liabilities = data.get("liabilities", {})
        return list(liabilities.values())
    except Exception as e:
        print(f"Warning: Could not load liabilities: {e}")
        return []


def get_liability(liability_id: str) -> dict | None:
    """Get a single liability by ID."""
    try:
        data = load_portfolios()
        return data.get("liabilities", {}).get(liability_id)
    except Exception:
        return None


def save_liability(liability: dict) -> dict:
    """
    Save a new liability. Returns the created liability with ID.

    Args:
        liability: Dict with name, balance, type, interest_rate, currency, notes

    Returns:
        Dict with success status and the created liability
    """
    from datetime import datetime

    try:
        data = load_portfolios()

        # Ensure liabilities dict exists
        if "liabilities" not in data:
            data["liabilities"] = {}

        # Generate ID and set timestamps
        liability_id = generate_liability_id()
        now = datetime.utcnow().isoformat() + "Z"

        liability_record = {
            "id": liability_id,
            "name": liability.get("name"),
            "type": liability.get("type", "other"),
            "balance": float(liability.get("balance", 0)),
            "interest_rate": liability.get("interest_rate"),
            "currency": liability.get("currency", "USD"),
            "notes": liability.get("notes"),
            "created_at": now,
            "updated_at": now,
        }

        data["liabilities"][liability_id] = liability_record
        save_portfolios(data)

        return {"success": True, "liability": liability_record}
    except Exception as e:
        return {"success": False, "error": str(e)}


def update_liability(liability_id: str, updates: dict) -> dict:
    """
    Update an existing liability.

    Args:
        liability_id: The liability ID
        updates: Dict of fields to update (name, balance, type, interest_rate, notes)

    Returns:
        Dict with success status and updated liability
    """
    from datetime import datetime

    try:
        data = load_portfolios()

        if liability_id not in data.get("liabilities", {}):
            return {"success": False, "error": f"Liability '{liability_id}' not found"}

        liability = data["liabilities"][liability_id]

        # Update allowed fields
        if "name" in updates and updates["name"] is not None:
            liability["name"] = updates["name"]
        if "balance" in updates and updates["balance"] is not None:
            liability["balance"] = float(updates["balance"])
        if "type" in updates and updates["type"] is not None:
            liability["type"] = updates["type"]
        if "interest_rate" in updates:
            liability["interest_rate"] = updates["interest_rate"]
        if "notes" in updates:
            liability["notes"] = updates["notes"]

        liability["updated_at"] = datetime.utcnow().isoformat() + "Z"

        save_portfolios(data)

        return {"success": True, "liability": liability}
    except Exception as e:
        return {"success": False, "error": str(e)}


def delete_liability(liability_id: str) -> dict:
    """
    Delete a liability.

    Args:
        liability_id: The liability ID to delete

    Returns:
        Dict with success status
    """
    try:
        data = load_portfolios()

        if liability_id not in data.get("liabilities", {}):
            return {"success": False, "error": f"Liability '{liability_id}' not found"}

        deleted = data["liabilities"].pop(liability_id)
        save_portfolios(data)

        return {"success": True, "deleted": deleted}
    except Exception as e:
        return {"success": False, "error": str(e)}
