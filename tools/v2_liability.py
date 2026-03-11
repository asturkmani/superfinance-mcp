"""Consolidated liability management tool."""

import json
from typing import Optional, Literal

from helpers.portfolio import (
    load_liabilities,
    save_liability as _save_liability,
    update_liability as _update_liability,
    delete_liability as _delete_liability,
)


def register_liability_v2(server):
    """Register consolidated liability tool."""

    @server.tool()
    def liability(
        action: str,
        liability_id: str = None,
        name: str = None,
        balance: float = None,
        type: Optional[Literal["mortgage", "auto_loan", "credit_card", "student_loan", "personal_loan", "line_of_credit", "other"]] = "other",
        interest_rate: Optional[float] = None,
        currency: str = "USD",
        notes: Optional[str] = None
    ) -> str:
        """
        Manage liabilities (debts, mortgages, loans).

        Actions:
        - list: List all liabilities with totals
        - add: Add a new liability
        - update: Update existing liability
        - remove: Remove a liability

        Args:
            action: Action to perform (list|add|update|remove)
            liability_id: Liability ID for update/remove actions
            name: Display name (e.g., "Home Mortgage", "Chase Visa")
            balance: Current balance owed
            type: Type (mortgage|auto_loan|credit_card|student_loan|personal_loan|line_of_credit|other)
            interest_rate: Annual interest rate as percentage (e.g., 4.5 for 4.5%)
            currency: Currency code (default "USD")
            notes: Optional notes

        Returns:
            JSON with liability data or operation result

        Examples:
            liability(action="list")
            liability(action="add", name="Home Mortgage", balance=450000, type="mortgage", interest_rate=4.5)
            liability(action="update", liability_id="liab_123", balance=425000)
            liability(action="remove", liability_id="liab_123")
        """
        try:
            if action == "list":
                liabilities = load_liabilities()
                total_balance = sum(l.get("balance", 0) for l in liabilities)
                liabilities.sort(key=lambda l: l.get("balance", 0), reverse=True)

                return json.dumps({
                    "success": True,
                    "count": len(liabilities),
                    "total_balance": round(total_balance, 2),
                    "currency": "USD",
                    "liabilities": liabilities
                }, indent=2)

            elif action == "add":
                if not name or balance is None:
                    return json.dumps({
                        "error": "name and balance required for add action"
                    }, indent=2)

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

            elif action == "update":
                if not liability_id:
                    return json.dumps({
                        "error": "liability_id required for update action"
                    }, indent=2)

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
                        "hint": "Provide at least one field to update"
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

            elif action == "remove":
                if not liability_id:
                    return json.dumps({
                        "error": "liability_id required for remove action"
                    }, indent=2)

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

            else:
                return json.dumps({
                    "error": f"Invalid action: {action}",
                    "valid_actions": ["list", "add", "update", "remove"]
                }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
