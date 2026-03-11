"""Vault authentication — OAuth 2.1 provider backed by SQLite."""

import secrets
import time
import json

from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from pydantic import AnyHttpUrl

from fastmcp.server.auth.auth import (
    ClientRegistrationOptions,
    OAuthProvider,
    RevocationOptions,
)


AUTH_CODE_EXPIRY = 5 * 60  # 5 min
ACCESS_TOKEN_EXPIRY = 60 * 60  # 1 hour
REFRESH_TOKEN_EXPIRY = 30 * 24 * 60 * 60  # 30 days


class VaultOAuthProvider(OAuthProvider):
    """
    OAuth 2.1 provider for Vault MCP server.
    
    Stores OAuth clients, codes, and tokens in-memory (they're ephemeral).
    User lookup goes through SQLite via API tokens.
    
    The flow:
    1. Claude registers as an OAuth client (dynamic registration)
    2. Claude redirects user to /authorize
    3. We show a login page, user enters email+password
    4. We issue an auth code, redirect back to Claude
    5. Claude exchanges code for access token
    6. Access token = our vault_ API token (used for user lookup)
    """

    def __init__(self, base_url: str):
        super().__init__(
            base_url=base_url,
            client_registration_options=ClientRegistrationOptions(
                enabled=True,
                valid_scopes=["vault:full"],
                default_scopes=["vault:full"],
            ),
            revocation_options=RevocationOptions(enabled=True),
        )
        # In-memory stores (ephemeral, survives until restart)
        self.clients: dict[str, OAuthClientInformationFull] = {}
        self.auth_codes: dict[str, AuthorizationCode] = {}
        self.tokens: dict[str, AccessToken] = {}
        self.refresh_tokens: dict[str, RefreshToken] = {}
        # Map auth code -> user_id (AuthorizationCode has no metadata field)
        self.code_user_map: dict[str, str] = {}

    # === Client Registration ===

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        return self.clients.get(client_id)

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        self.clients[client_info.client_id] = client_info

    # === Authorization ===

    async def authorize(
        self, client: OAuthClientInformationFull, params: AuthorizationParams
    ) -> str:
        """
        Called when user hits /authorize. We need to show a login page.
        
        Instead of auto-approving, redirect to our login page which will
        collect credentials and then redirect back with the auth code.
        """
        # Store the auth request params so the login page can complete it
        request_id = secrets.token_urlsafe(16)
        
        # Store pending auth request
        self._pending_auth = getattr(self, '_pending_auth', {})
        self._pending_auth[request_id] = {
            'client': client,
            'params': params,
            'created_at': time.time(),
        }
        
        # Redirect to our login page
        base = str(self.base_url).rstrip('/')
        return f"{base}/vault-login?request_id={request_id}"

    async def complete_authorization(self, request_id: str, user_id: str) -> str:
        """Complete the OAuth flow after user logs in. Returns redirect URL."""
        pending = getattr(self, '_pending_auth', {})
        auth_request = pending.get(request_id)
        if not auth_request:
            raise AuthorizeError(error="invalid_request", error_description="Invalid or expired login request")
        
        client = auth_request['client']
        params = auth_request['params']
        
        # Clean up
        del pending[request_id]
        
        # Generate authorization code
        code_str = secrets.token_urlsafe(32)
        
        now = time.time()
        auth_code = AuthorizationCode(
            code=code_str,
            client_id=client.client_id,
            redirect_uri=params.redirect_uri,
            redirect_uri_provided_explicitly=params.redirect_uri_provided_explicitly,
            code_challenge=params.code_challenge,
            scopes=params.scopes or ["vault:full"],
            expires_at=now + AUTH_CODE_EXPIRY,
        )
        self.auth_codes[code_str] = auth_code
        # Store user_id separately (AuthorizationCode has no metadata field)
        self.code_user_map[code_str] = user_id
        
        # Build redirect URI back to Claude
        return construct_redirect_uri(
            redirect_uri_base=str(params.redirect_uri),
            code=code_str,
            state=params.state,
        )

    # === Token Exchange ===

    async def load_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: str
    ) -> AuthorizationCode | None:
        code = self.auth_codes.get(authorization_code)
        if code and code.client_id == client.client_id:
            if code.expires_at and time.time() > code.expires_at:
                del self.auth_codes[authorization_code]
                return None
            return code
        return None

    async def exchange_authorization_code(
        self, client: OAuthClientInformationFull, authorization_code: AuthorizationCode
    ) -> OAuthToken:
        """Exchange auth code for tokens. Creates a vault_ API token for the user."""
        import traceback
        from db import queries
        
        print(f"[OAuth] exchange_authorization_code called for code={authorization_code.code[:8]}...")
        print(f"[OAuth] code_user_map keys: {list(self.code_user_map.keys())[:5]}")
        
        # Get user_id from our code->user mapping
        user_id = self.code_user_map.pop(authorization_code.code, None)
        print(f"[OAuth] user_id from map: {user_id}")
        
        if not user_id:
            raise TokenError(error="invalid_grant", error_description="No user associated with this code")
        
        try:
            # Create a real vault_ API token for this user
            token_str = queries.create_api_token(user_id, name=f"claude-{client.client_id[:8]}")
            print(f"[OAuth] Created token: {token_str[:12]}...")
        except Exception as e:
            print(f"[OAuth] ERROR creating token: {e}")
            traceback.print_exc()
            raise
        
        now = time.time()
        access_token = AccessToken(
            token=token_str,
            client_id=client.client_id,
            scopes=authorization_code.scopes or ["vault:full"],
            expires_at=now + ACCESS_TOKEN_EXPIRY,
        )
        self.tokens[token_str] = access_token
        
        # Create refresh token
        refresh_str = secrets.token_urlsafe(32)
        refresh_token = RefreshToken(
            token=refresh_str,
            client_id=client.client_id,
            scopes=authorization_code.scopes or ["vault:full"],
        )
        self.refresh_tokens[refresh_str] = refresh_token
        
        # Clean up auth code
        if authorization_code.code in self.auth_codes:
            del self.auth_codes[authorization_code.code]
        
        return OAuthToken(
            access_token=token_str,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRY,
            refresh_token=refresh_str,
            scope=" ".join(authorization_code.scopes or ["vault:full"]),
        )

    async def load_access_token(self, token: str) -> AccessToken | None:
        """Verify access token — checks both OAuth tokens and direct vault_ tokens."""
        # First check OAuth-issued tokens
        at = self.tokens.get(token)
        if at:
            if at.expires_at and time.time() > at.expires_at:
                del self.tokens[token]
                return None
            return at
        
        # Fall back to direct vault_ token lookup in DB
        from db import queries
        user = queries.get_user_by_token(token)
        if user:
            return AccessToken(
                token=token,
                client_id=user["id"],
                scopes=["vault:full"],
                expires_at=None,
            )
        return None

    async def load_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: str
    ) -> RefreshToken | None:
        rt = self.refresh_tokens.get(refresh_token)
        if rt and rt.client_id == client.client_id:
            return rt
        return None

    async def exchange_refresh_token(
        self, client: OAuthClientInformationFull, refresh_token: RefreshToken, scopes: list[str]
    ) -> OAuthToken:
        """Refresh the access token."""
        from db import queries
        
        # Find the user for this client's existing tokens
        # Look through tokens to find one matching this client
        user_id = None
        for token_str, at in self.tokens.items():
            if at.client_id == client.client_id:
                user = queries.get_user_by_token(token_str)
                if user:
                    user_id = user["id"]
                    break
        
        if not user_id:
            raise TokenError(error="invalid_grant", error_description="Cannot refresh — user not found")
        
        # Create new access token
        new_token_str = queries.create_api_token(user_id, name=f"claude-refresh-{client.client_id[:8]}")
        
        now = time.time()
        new_access_token = AccessToken(
            token=new_token_str,
            client_id=client.client_id,
            scopes=scopes or refresh_token.scopes or ["vault:full"],
            expires_at=now + ACCESS_TOKEN_EXPIRY,
        )
        self.tokens[new_token_str] = new_access_token
        
        # Rotate refresh token
        new_refresh_str = secrets.token_urlsafe(32)
        new_refresh_token = RefreshToken(
            token=new_refresh_str,
            client_id=client.client_id,
            scopes=scopes or refresh_token.scopes or ["vault:full"],
        )
        
        # Remove old refresh token
        if refresh_token.token in self.refresh_tokens:
            del self.refresh_tokens[refresh_token.token]
        self.refresh_tokens[new_refresh_str] = new_refresh_token
        
        return OAuthToken(
            access_token=new_token_str,
            token_type="bearer",
            expires_in=ACCESS_TOKEN_EXPIRY,
            refresh_token=new_refresh_str,
            scope=" ".join(scopes or refresh_token.scopes or ["vault:full"]),
        )

    # === Revocation ===

    async def revoke_token(
        self, client: OAuthClientInformationFull, token: str, token_type_hint: str | None = None
    ) -> None:
        self.tokens.pop(token, None)
        self.refresh_tokens.pop(token, None)
