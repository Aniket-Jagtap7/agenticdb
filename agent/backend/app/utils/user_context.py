from contextvars import ContextVar
from typing import Any


_current_user: ContextVar[
    dict[str, Any] | None
] = ContextVar("current_authenticated_user", default=None,)


def set_current_user(user: dict[str, Any]):
    """
    Attach an authenticated user to the current asynchronous
    agent execution context.
    """
    return _current_user.set(user)


def reset_current_user(token) -> None:
    """
    Restore the previous authenticated-user context.
    """

    _current_user.reset(token)


def get_current_user_context() -> dict[str, Any]:
    """
    Return the authenticated user for the current agent
    execution.

    This can later be used by authorization and audit code.
    """

    user = _current_user.get()

    if user is None:
        raise RuntimeError(
            "No authenticated user is available "
            "in the current execution context."
        )

    return user


def get_optional_current_user_context(
) -> dict[str, Any] | None:
    """
    Return the current user if one exists.

    This is useful for logging code that may run outside an
    authenticated request.
    """

    return _current_user.get()