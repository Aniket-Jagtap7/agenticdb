from typing import Any
from fastapi import WebSocket
from starlette.concurrency import run_in_threadpool
from auth.config import settings
from auth.dependencies import authenticate_session_token

UNAUTHENTICATED_WEBSOCKET_CODE = 4401
FORBIDDEN_WEBSOCKET_CODE = 4403


async def authenticate_websocket(websocket: WebSocket) -> dict[str, Any] | None:
   
    session_token = websocket.cookies.get(settings.session_cookie_name)

    if not session_token:
        return None
    
    user = await run_in_threadpool(authenticate_session_token, session_token)
    return user


async def reject_unauthenticated_websocket(websocket: WebSocket) -> None:
   
    await websocket.accept()

    await websocket.send_json(
        {
            "type": "authentication_error",
            "code": "UNAUTHENTICATED",
            "message": ("Your session is missing, invalid or expired. Please sign in again."),
        }
    )

    await websocket.close(
        code=UNAUTHENTICATED_WEBSOCKET_CODE,
        reason="Authentication required",
    )