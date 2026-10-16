from typing import Any


USER_ROLE = "user"
ADMIN_ROLE = "admin"
VALID_ROLES = {USER_ROLE, ADMIN_ROLE}


class AuthorizationError(PermissionError):
    """
    Raised when an authenticated user attempts to access
    functionality that their role does not allow.
    """


def get_user_role(user: dict[str, Any]) -> str:
    role = str(user.get("role", "")).strip().lower()

    if role not in VALID_ROLES:
        raise AuthorizationError(
            "The authenticated user has an invalid role."
        )

    return role


def is_admin(user: dict[str, Any]) -> bool:
    return get_user_role(user) == ADMIN_ROLE


def ensure_admin(user: dict[str, Any]) -> None:
    if not is_admin(user):
        raise AuthorizationError("Only administrators can access the Admin Agent.")
