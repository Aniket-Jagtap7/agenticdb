from fastapi import Cookie, HTTPException, status
from auth.config import settings
from auth.repository import find_user_by_session_hash, update_session_last_seen
from auth.security import hash_session_token



def authenticate_session_token(
        session_token: str | 
        None, 
        *, 
        update_last_seen: bool = True,
) -> dict | None:
    
    if not session_token:
        return None

    token_hash = hash_session_token(session_token)
    user = find_user_by_session_hash(token_hash)

    if user is None:
        return None

    if update_last_seen:
        update_session_last_seen(user["session_id"])

    return user


def get_current_user(
    session_token: str | None = Cookie(
        default=None,
        alias=settings.session_cookie_name,
    ),
) -> dict:
   
    user = authenticate_session_token(session_token)

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=("The authentication session is invalid or expired.")
        )

    return user