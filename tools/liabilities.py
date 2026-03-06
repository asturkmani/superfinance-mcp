"""Liability management tools."""

import json
from typing import Optional, Literal

from helpers.portfolio import (
    load_liabilities,
    save_liability as _save_liability,
    update_liability as _update_liability,
    delete_liability as _delete_liability,
)


def register_liability_tools(server):
    """Register liability tools with the server."""

    @server.tool()
    def list_liabilities() -> str:
        """
        List all liabilities with totals.

        Returns all tracked liabilities (mortgages, loans, credit cards, etc.)
        with a total balance for net worth calculations.

        Returns:
            JSON with list of liabilities and total balance
        """
        liabilities = load_liabilities()

        # Calculate total
        total_balance = sum(l.get("balance", 0) for l in liabilities)

        # Sort by balance descending
        liabilities.sort(key=lambda l: l.get("balance", 0), reverse=True)

        return json.dumps({
            "success": True,
            "count": len(liabilities),
            "total_balance": round(total_balance, 2),
            "currency": "USD",  # Default, individual liabilities may vary
            "liabilities": liabilities
        }, indent=2)

    @server.tool()
    def add_liability(
        name: str,
        balance: float,
        type: Optional[Literal["mortgage", "auto_loan", "credit_card", "student_loan", "personal_loan", "line_of_credit", "other"]] = "other",
        interest_rate: Optional[float] = None,
        currency: str = "USD",
        notes: Optional[str] = None,
    ) -> str:
        """
        Add a new liability to track.

        Track mortgages, loans, credit cards, and other debts for net worth calculations.

        Args:
            name: Display name (e.g., "Home Mortgage", "Chase Visa")
            balance: Current balance owed
            type: Type of liability - mortgage, auto_loan, credit_card, student_loan, personal_loan, line_of_credit, other
            interest_rate: Optional annual interest rate as percentage (e.g., 4.5 for 4.5%)
            currency: Currency code (default "USD")
            notes: Optional notes (e.g., "Primary residence", "Paid monthly")

        Returns:
            JSON confirming liability was added

        Examples:
            add_liability(name="Home Mortgage", balance=450000, type="mortgage", interest_rate=4.5)
            add_liability(name="Car Loan", balance=35000, type="auto_loan", interest_rate=6.9)
            add_liability(name="Chase Sapphire", balance=5000, type="credit_card")
        """
        result = _save_liability({
            "name": name,
            "balance": balance,
            "type": type,
            "interest_rate": interest_rate,
            "currency": currency.upper(),
            "notes": notes,
        })

        if result.get("success"):
            liability = result["liability"]
            return json.dumps({
                "success": True,
                "liability_id": liability["id"],
                "name": liability["name"],
                "balance": liability["balance"],
                "type": liability["type"],
                "message": f"Liability '{name}' added with balance {currency.upper()} {balance:,.2f}"
            }, indent=2)
        else:
            return json.dumps({"error": result.get("error")}, indent=2)

    @server.tool()
    def update_liability(
        liability_id: str,
        name: Optional[str] = None,
        balance: Optional[float] = None,
        type: Optional[Literal["mortgage", "auto_loan", "credit_card", "student_loan", "personal_loan", "line_of_credit", "other"]] = None,
        interest_rate: Optional[float] = None,
        notes: Optional[str] = None,
    ) -> str:
        """
        Update an existing liability.

        Only provided fields are updated; others remain unchanged.

        Args:
            liability_id: The liability ID (from list_liabilities)
            name: New display name
            balance: New current balance
            type: New type (mortgage, auto_loan, credit_card, etc.)
            interest_rate: New interest rate (set to 0 to clear)
            notes: New notes (set to empty string to clear)

        Returns:
            JSON confirming update

        Examples:
            update_liability(liability_id="liab_abc123", balance=425000)
            update_liability(liability_id="liab_abc123", name="Primary Mortgage", interest_rate=3.75)
        """
        updates = {}
        if name is not None:
            updates["name"] = name
        if balance is not None:
            updates["balance"] = balance
        if type is not None:
            updates["type"] = type
        if interest_rate is not None:
            updates["interest_rate"] = interest_rate if interest_rate != 0 else None
        if notes is not None:
            updates["notes"] = notes if notes else None

        if not updates:
            return json.dumps({
                "error": "No updates provided",
                "hint": "Provide at least one field to update (name, balance, type, interest_rate, notes)"
            }, indent=2)

        result = _update_liability(liability_id, updates)

        if result.get("success"):
            liability = result["liability"]
            return json.dumps({
                "success": True,
                "liability_id": liability_id,
                "updated": list(updates.keys()),
                "liability": liability,
                "message": "Liability updated"
            }, indent=2)
        else:
            return json.dumps({"error": result.get("error")}, indent=2)

    @server.tool()
    def remove_liability(liability_id: str) -> str:
        """
        Remove a liability.

        Args:
            liability_id: The liability ID to remove (from list_liabilities)

        Returns:
            JSON confirming removal
        """
        result = _delete_liability(liability_id)

        if result.get("success"):
            deleted = result["deleted"]
            return json.dumps({
                "success": True,
                "liability_id": liability_id,
                "name": deleted.get("name"),
                "message": f"Liability '{deleted.get('name')}' removed"
            }, indent=2)
        else:
            return json.dumps({"error": result.get("error")}, indent=2)
