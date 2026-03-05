"""Get current user from FastMCP auth context."""

from db import queries


def get_current_user_id() -> str:
    """Get user_id from FastMCP auth context, falling back to default user.
    
    When running with auth (HTTP mode), extracts user from the verified token.
    When running without auth (stdio mode / local dev), returns default user.
    """
    try:
        from fastmcp.server.dependencies import get_context
        ctx = get_context()
        # client_id is set to user_id in VaultTokenVerifier
        if ctx and ctx.client_id:
            return ctx.client_id
    except (RuntimeError, ImportError):
        pass
    
    # Fallback for local dev / stdio mode
    return queries.get_or_create_default_user()
