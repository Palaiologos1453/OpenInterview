from __future__ import annotations

from fastapi import Request, WebSocket
from fastapi.responses import JSONResponse

from .security import verify_token
from .settings import require_auth
from .storage import Storage


PUBLIC_PATHS = {
    "/health",
    "/openapi.json",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/v1/users",
}


async def auth_middleware(request: Request, call_next):
    if _is_public(request.url.path) or not require_auth():
        return await call_next(request)

    token = _extract_bearer(request.headers.get("Authorization"))
    if not token:
        return JSONResponse(status_code=401, content={"detail": "Missing bearer token."})

    storage = Storage()
    user_id = request.headers.get("X-OpenInterview-User")
    if not user_id:
        return JSONResponse(status_code=401, content={"detail": "Missing X-OpenInterview-User header."})
    user = storage.get_user_by_id(user_id)
    if not user or not verify_token(token, user["token_hash"]):
        return JSONResponse(status_code=401, content={"detail": "Invalid bearer token."})

    request.state.user_id = user_id
    return await call_next(request)


async def authenticate_websocket(websocket: WebSocket) -> bool:
    if not require_auth():
        return True

    token = websocket.query_params.get("token") or _extract_bearer(
        websocket.headers.get("Authorization")
    )
    user_id = websocket.query_params.get("user_id") or websocket.headers.get("X-OpenInterview-User")
    if not token or not user_id:
        await websocket.close(code=1008)
        return False

    user = Storage().get_user_by_id(user_id)
    if not user or not verify_token(token, user["token_hash"]):
        await websocket.close(code=1008)
        return False

    return True


def _extract_bearer(value: str | None) -> str | None:
    if not value:
        return None
    prefix = "Bearer "
    if not value.startswith(prefix):
        return None
    return value[len(prefix):].strip()


def _is_public(path: str) -> bool:
    return path in PUBLIC_PATHS
