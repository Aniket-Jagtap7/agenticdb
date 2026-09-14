from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from auth.config import settings
from auth.dependencies import get_current_user
from auth.repository import create_session, find_user_by_username, revoke_session
from auth.schemas import CurrentUserResponse, LoginRequest, LoginResponse, LogoutResponse, UserResponse
from auth.security import generate_session_token, hash_session_token, verify_password


router = APIRouter(prefix="/auth", tags=["Authentication"])


def create_user_response(user: dict) -> UserResponse:
    return UserResponse(
        id=user["id"],
        username=user["username"],
        email=user.get("email"),
        display_name=user["display_name"],
        role=user["role"],
    )


@router.post("/login", response_model=LoginResponse)
def login(login_request: LoginRequest, request: Request, response: Response):
    user = find_user_by_username(login_request.username)

    valid_credentials = (
        user is not None
        and bool(user["is_active"])
        and verify_password(
            login_request.password,
            user["password_hash"],
        )
    )

    if not valid_credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=("Invalid username or password.")
        )

    session_token = (generate_session_token())
    session_token_hash = (hash_session_token(session_token))

    expires_at = (
        datetime.now(timezone.utc)
        + timedelta(hours=settings.session_hours)
    ).replace(tzinfo=None)

    client_ip = (request.client.host if request.client else None)
    user_agent = request.headers.get("user-agent")

    if user_agent:
        user_agent = user_agent[:255]

    create_session(
        user_id=user["id"],
        token_hash=session_token_hash,
        expires_at=expires_at,
        ip_address=client_ip,
        user_agent=user_agent,
    )

    response.set_cookie(
        key=settings.session_cookie_name,
        value=session_token,
        max_age=(settings.session_hours * 60 * 60),
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        path="/",
    )

    return LoginResponse(authenticated=True, user=create_user_response(user))


@router.get("/me", response_model=CurrentUserResponse)
def get_me(current_user: dict = Depends(get_current_user)):
    return CurrentUserResponse(
        authenticated=True,
        user=create_user_response(current_user)
    )


@router.post("/logout", response_model=LogoutResponse)
def logout(
    response: Response,
    session_token: str | None = Cookie(default=None, alias=settings.session_cookie_name,)
):
    if session_token:
        token_hash = hash_session_token(session_token)
        revoke_session(token_hash)

    response.delete_cookie(key=settings.session_cookie_name, path="/")
    return LogoutResponse(authenticated=False, message="Logged out successfully.")