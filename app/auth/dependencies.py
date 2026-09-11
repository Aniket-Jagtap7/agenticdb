from fastapi import Cookie, HTTPException , status
from auth.config import settings
from auth.repository import find_user_by_session_hash, update_session_last_seen
from auth.security import hash_session_token


def get_current_user(
        session_token: str | None = Cookie(
        default=None,
        alias=settings.session_cookie_name,
    ),
) -> dict:
    if not session_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication is required.",
        )

    token_hash = hash_session_token(session_token)
    user = find_user_by_session_hash(token_hash)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=("The authentication session is invalid or expired.")
        )

    update_session_last_seen(user["session_id"])

    return user