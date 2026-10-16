from contextvars import ContextVar
from typing import Any, Awaitable, Callable


HumanInputHandler = Callable[
    [Any],
    Awaitable[Any],
]


_human_input_handler: ContextVar[HumanInputHandler | None] = ContextVar("human_input_handler", default=None)


def set_human_input_handler(handler: HumanInputHandler,):
    """
    Register the WebSocket human-input handler for the
    current agent execution context.
    """

    return _human_input_handler.set(handler)


def reset_human_input_handler(token) -> None:
    """
    Restore the previous handler after the agent execution.
    """

    _human_input_handler.reset(token)


async def request_human_input(interrupt_value: Any,) -> Any:
    """
    Send an interrupt to the frontend and wait for the
    user's response.

    This function can be called by deeply nested graph tools
    without importing FastAPI main.py.
    """

    handler = _human_input_handler.get()

    if handler is None:
        raise RuntimeError(
            "No human-input handler is registered for "
            "the current agent execution."
        )

    return await handler(interrupt_value)