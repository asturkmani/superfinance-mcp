"""Vault authentication via API tokens."""

from fastmcp.server.auth import TokenVerifier, AccessToken
from db import queries


class VaultTokenVerifier(TokenVerifier):
    """Verify API tokens against SQLite database."""
    
    async def verify_token(self, token: str) -> AccessToken | None:
        user = queries.get_user_by_token(token)
        if not user:
            return None
        return AccessToken(
            token=token,
            client_id=user["id"],
            scopes=["vault:full"],
            expires_at=None,
            claims={"user_id": user["id"], "email": user["email"], "name": user.get("name")},
        )
