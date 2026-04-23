from supabase import AsyncClient, create_async_client

from app.config import settings

_service_client: AsyncClient | None = None


async def service_client() -> AsyncClient:
    """Service-role client — BYPASSES RLS.

    Use for: usage_log writes, match_knowledge_nodes RPC, admin operations.
    Never use for user-content reads/writes — you'd have to filter manually,
    and that's how leaks happen.
    """
    global _service_client
    if _service_client is None:
        _service_client = await create_async_client(
            settings.SUPABASE_URL,
            settings.SUPABASE_SERVICE_ROLE_KEY,
        )
    return _service_client


async def user_client(jwt: str) -> AsyncClient:
    """User-scoped client — HONORS RLS via the user's JWT.

    Use for every read/write on behalf of a user. RLS enforces user_id — do
    not add manual .eq("user_id", ...) filters in routes.
    """
    client = await create_async_client(
        settings.SUPABASE_URL,
        settings.SUPABASE_ANON_KEY,
    )
    client.postgrest.auth(jwt)
    return client
