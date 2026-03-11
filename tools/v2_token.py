"""Consolidated token management tool."""

import json

from db import queries
from helpers.user_context import get_current_user_id


def register_token_v2(server):
    """Register consolidated token tool."""

    @server.tool()
    def token(
        action: str,
        name: str = "default",
        token_value: str = None
    ) -> str:
        """
        Manage API tokens.

        Actions:
        - create: Create a new API token
        - list: List all tokens (masked for security)
        - revoke: Revoke a token

        Args:
            action: Action to perform (create|list|revoke)
            name: Token name for create action (e.g., "desktop", "mobile")
            token_value: Token string to revoke for revoke action

        Returns:
            JSON with token data or operation result

        Examples:
            token(action="create", name="desktop")
            token(action="list")
            token(action="revoke", token_value="abc...")
        """
        try:
            user_id = get_current_user_id()

            if action == "create":
                token = queries.create_api_token(user_id, name)
                return json.dumps({
                    "token": token,
                    "name": name,
                    "message": "Save this token — it won't be shown again"
                }, indent=2)

            elif action == "list":
                tokens = queries.list_user_tokens(user_id)
                return json.dumps(tokens, indent=2)

            elif action == "revoke":
                if not token_value:
                    return json.dumps({
                        "error": "token_value required for revoke action"
                    }, indent=2)
                success = queries.revoke_token(token_value)
                return json.dumps({"success": success}, indent=2)

            else:
                return json.dumps({
                    "error": f"Invalid action: {action}",
                    "valid_actions": ["create", "list", "revoke"]
                }, indent=2)

        except Exception as e:
            return json.dumps({"error": str(e)}, indent=2)
