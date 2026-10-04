import ast
import json
import logging
import uuid
import time
from typing import Any, Awaitable, Callable
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError
from agents.admin_agent import invoke_admin_agent
from agents.main_agent import invoke_main_agent
from utils.hitl_context import reset_human_input_handler, set_human_input_handler
from utils.user_context import reset_current_user, set_current_user
from auth.router import router as auth_router
from auth.websocket import authenticate_websocket, reject_unauthenticated_websocket, FORBIDDEN_WEBSOCKET_CODE
from auth.authorization import AuthorizationError, ensure_admin 
from utils.logging_config import setup_logging


setup_logging(service_name="database-assistant-app", log_file_prefix="app")
logger = logging.getLogger(__name__)

app = FastAPI(title="Database AI Assistant")

# adding the auth router to the main app
app.include_router(auth_router)


EVENTS = {
    "read_db": "Agent working...",
    "delete_db_data": "Deleting records...",
    "update_db_data": "Updating records...",
    "write_db_data": "Writing records...",
    "get_tables": "Selecting source...",
    "get_columns": "Fetching schema...",
    "direct_execute_query": "Fetching data from source...",
    "employees": "Adding employee records...",
    "salaries": "Adding salary records...",
    "departments": "Adding department records...",
    "deparment_employees": "Adding department employee records...",
    "titles": "Adding title records...",
    "manager_of_departments": "Adding department manager records...",
}

TOOL_LIMIT_USER_MESSAGE = (
    "I couldn't complete this request because its tool processing "
    "limit was reached. Please narrow the request and try again."
)


AgentInvoker = Callable[[str], Awaitable[Any]]


def create_websocket_human_input_handler(websocket: WebSocket):
    """Create a HITL callback bound to the current WebSocket."""

    async def get_human_input(interrupt_value: Any) -> Any:
        logger.info("Human review requested")
        await websocket.send_json(
            {
                "type": "interrupt",
                "value": interrupt_value,
            }
        )

        while True:
            frontend_message = await websocket.receive_json()
            message_type = frontend_message.get("type")
            logger.debug("HITL frontend message received:message_type=%s", message_type)

            if message_type == "resume":
                if "value" not in frontend_message:
                    logger.warning("Invalid HITL resume message: reason=missing_value")
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "The resume message must contain a value.",
                        }
                    )
                    continue

                logger.info("Human review response received")
                return frontend_message["value"]

            if message_type == "exit":
                logger.info("Client requested exit during human review")
                raise WebSocketDisconnect(code=1000)

            logger.warning("Unexpected message while waiting for human review: message_type=%s", message_type)
            await websocket.send_json(
                {
                    "type": "error",
                    "message": ("The graph is waiting for human input. Please answer the popup."),
                }
            )

    return get_human_input


def parse_tool_message_content(content: Any) -> dict[str, Any] | None:
    """Parse a dictionary from ToolMessage.content when needed."""

    if isinstance(content, dict):
        return content

    text_value: str | None = None

    if isinstance(content, list):
        for item in content:
            if not isinstance(item, dict):
                continue

            if item.get("type") == "text" and item.get("text"):
                text_value = str(item["text"])
                break

    elif isinstance(content, str):
        text_value = content

    if not text_value:
        logger.debug("Tool message did not contain parseable text content")
        return None

    try:
        parsed_value = json.loads(text_value)
        if isinstance(parsed_value, dict):
            return parsed_value
        
    except json.JSONDecodeError:
        logger.debug("Tool content was not valid JSON, trying Python literal parsing")
        pass

    try:
        parsed_value = ast.literal_eval(text_value)
        if isinstance(parsed_value, dict):
            return parsed_value
        
    except (ValueError, SyntaxError):
        logger.debug("Tool content could not be parsed as a dictionary")
        return None

    return None


def extract_download_metadata(event: dict[str, Any]) -> dict[str, str] | None:
    """
    Extract file metadata only from direct_execute_query on_tool_end events.
    A read result that did not generate a CSV will not contain both
    file_name and download_url, so it is ignored automatically.
    """

    if event.get("event") != "on_tool_end":
        return None

    if event.get("name") != "direct_execute_query":
        return None

    tool_output = event.get("data", {}).get("output")
    if tool_output is None:
        return None

    structured_content: dict[str, Any] | None = None

    artifact = getattr(tool_output, "artifact", None)
    if isinstance(artifact, dict):
        candidate = artifact.get("structured_content")
        if isinstance(candidate, dict):
            structured_content = candidate

    # Fallback when artifact/structured_content is unavailable.
    if structured_content is None:
        content = getattr(tool_output, "content", None)
        structured_content = parse_tool_message_content(content)

    if not isinstance(structured_content, dict):
        return None

    file_name = structured_content.get("file_name")
    download_url = structured_content.get("download_url")

    if not file_name or not download_url:
        return None

    logger.debug("Download metadata extracted: file_name=%s", file_name)
    return {
        "message": str(structured_content.get("message", "The generated CSV file is ready.")),
        "file_name": str(file_name),
        "download_url": str(download_url),
    }


def normalize_chunk_content(content: Any) -> str:
    if isinstance(content, str):
        return content

    if isinstance(content, list):
        text_parts: list[str] = []

        for item in content:
            if isinstance(item, str):
                text_parts.append(item)
            elif isinstance(item, dict) and item.get("type") == "text":
                text_parts.append(str(item.get("text", "")))

        return "".join(text_parts)

    return ""


def find_tool_limit_error(error: BaseException) -> ToolCallLimitExceededError | None:
    """
    Find a tool-call limit exception in an exception chain.

    Nested agents may wrap the original exception using
    'raise ... from error'. This function follows the
    exception cause and context.
    """

    current_error: BaseException | None = error
    visited_errors: set[int] = set()

    while current_error is not None:
        error_identity = id(current_error)

        if error_identity in visited_errors:
            break

        visited_errors.add(error_identity)

        if isinstance(current_error, ToolCallLimitExceededError):
            return current_error

        current_error = (
            current_error.__cause__
            or current_error.__context__
        )

    return None


async def stream_agent(
    websocket: WebSocket, 
    invoke_agent: AgentInvoker,
    *,
    admin_only: bool = False
) -> None:

    authenticated_user = await authenticate_websocket(websocket)

    if authenticated_user is None:
        logger.warning(
            "Unauthenticated WebSocket rejected:" "agent=%s client=%s", 
            (websocket.client.host if websocket.client else "unknown")
        )
        await reject_unauthenticated_websocket(websocket)
        return

    if admin_only:
        try:
            ensure_admin(authenticated_user)

        except AuthorizationError as auth_error:
            logger.warning(
                "Admin Agent access denied: user_id=%s username=%s role=%s", 
                authenticated_user.get("id"), 
                authenticated_user.get("username"), 
                authenticated_user.get("role")
            )

            await websocket.accept()
            await websocket.send_json(
                {
                    "type": "authorization_error",
                    "code" : "FORBIDDEN",
                    "message": str(auth_error),
                }
            )

            await websocket.close(
                code = FORBIDDEN_WEBSOCKET_CODE,
                reason="Administrator access required",
            )

            return
            
    await websocket.accept()
    logger.info(
        "WebSocket authenticated: user_id=%s username=%s role=%s agent=%s client=%s", 
        authenticated_user.get("id"), 
        authenticated_user.get("username"), 
        authenticated_user.get("role"), 
        (websocket.client.host if websocket.client else "unknown")
    )
    get_human_input = create_websocket_human_input_handler(websocket)

    try:
        await websocket.send_json(
            {
                "type": "connected", 
                "message": "Database Assistant Started!",
                "user": {
                    "id": authenticated_user.get("id", ""),
                    "username": authenticated_user.get("username", ""),
                    "display_name": authenticated_user.get("display_name", ""),
                    "role": authenticated_user.get("role", ""),
                }
            }
        )

        while True:
            frontend_message = await websocket.receive_json()
            message_type = frontend_message.get("type")
            request_id = uuid.uuid4().hex
            started_at = time.perf_counter()
            logger.info(
                "Agent request started: request_id=%s user_id=%s agent=%s message_length=%s",
                request_id,
                authenticated_user.get("id"),
            )

            if message_type == "exit":
                logger.info(
                    "Client requested WebSocket exit: user_id=%s agent=%s",
                    authenticated_user.get("id")
                )
                await websocket.send_json({"type": "goodbye", "message": "Goodbye!"})
                await websocket.close(code=1000)
                return

            if message_type != "message":
                logger.warning(
                    "Unexpected WebSocket message: user_id=%s agent=%s message_type=%s",
                    authenticated_user.get("id"),
                    message_type
                )
                await websocket.send_json({"type": "error", "message": "Expected a user message."})
                continue

            user_message = str(frontend_message.get("content", "")).strip()

            if not user_message:
                logger.warning(
                    "Empty user message rejected: user_id=%s agent=%s",
                    authenticated_user.get("id")
                )
                await websocket.send_json({"type": "error", "message": "Message cannot be empty."})
                continue

            handler_token = set_human_input_handler(get_human_input)
            user_context_token = set_current_user(authenticated_user)
            generated_files: list[dict[str, str]] = []

            try:
                stream = await invoke_agent(user_message)

                async for event in stream:
                    event_type = event.get("event")

                    if event_type == "on_tool_start":
                        tool_name = event.get("name", "")
                        status_message = EVENTS.get(tool_name)

                        if status_message:
                            await websocket.send_json({"type": "status", "content": status_message})

                    elif event_type == "on_tool_end":
                        download_metadata = extract_download_metadata(event)

                        if download_metadata is not None:
                            download_url = download_metadata["download_url"]

                            is_duplicate = any(
                                existing["download_url"] == download_url
                                for existing in generated_files
                            )

                            if not is_duplicate:
                                generated_files.append(download_metadata)
                                print("Captured generated file:", download_metadata)
                                logger.info(
                                    "Generated file captured: request_id=%s user_id=%s file_name=%s",
                                    request_id,
                                    authenticated_user.get("id"),
                                    download_metadata["file_name"],
                                )

                    elif event_type == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        raw_content = getattr(chunk, "content", "")
                        content = normalize_chunk_content(raw_content)

                        if content:
                            await websocket.send_json(
                                {
                                    "type": "chunk",
                                    "content": content,
                                }
                            )

                # The agent stream has ended. Sending files after all model text,
                for generated_file in generated_files:
                    await websocket.send_json(
                        {
                            "type": "file",
                            "message": generated_file["message"],
                            "file_name": generated_file["file_name"],
                            "download_url": generated_file["download_url"],
                        }
                    )

                await websocket.send_json({"type": "complete",})

            except WebSocketDisconnect:
                raise

            except Exception as agent_error:
                limit_error = find_tool_limit_error(agent_error)

                if limit_error is not None:
                    logger.warning(
                        "Agent processing limit reached: request_id=%s user_id=%s agent=%s run_count=%s run_limit=%s "
                        "thread_count=%s thread_limit=%s",
                        request_id,
                        authenticated_user.get("id"),
                        getattr(limit_error, "run_count", None),
                        getattr(limit_error, "run_limit", None),
                        getattr(limit_error, "thread_count", None),
                        getattr(limit_error, "thread_limit", None),
                    )

                    await websocket.send_json(
                        {
                            "type" : "chunk",
                            "content" : TOOL_LIMIT_USER_MESSAGE
                        }
                    )

                else:
                    logger.exception(
                        "Agent execution failed:crequest_id=%s user_id=%s agent=%s",
                        request_id,
                        authenticated_user.get("id"),
                    )
                    
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": ("The agent could not complete the request. Please try again.")
                        }
                    )


            finally:
                await websocket.send_json({"type": "complete"})
                reset_current_user(user_context_token)
                reset_human_input_handler(handler_token)

    except WebSocketDisconnect:
        logger.info(
            "WebSocket client disconnected: user_id=%s username=%s agent=%s",
            authenticated_user.get("id"),
            authenticated_user.get("username"),
        )

    except Exception as error:
        logger.exception(
            "Unexpected WebSocket error: user_id=%s username=%s agent=%s",
            authenticated_user.get("id"),
            authenticated_user.get("username")
        )

        try:
            await websocket.send_json({"type": "error", "message": str(error)})
            
        except Exception:
            logger.debug(
                "Unable to send WebSocket error response because the connection is no longer available",
                exc_info=True
            )


@app.websocket("/chat")
async def user_chat(websocket: WebSocket) -> None:
    await stream_agent(
        websocket=websocket,
        invoke_agent=invoke_main_agent,
        admin_only=False,
    )


@app.websocket("/admin")
async def admin_chat(websocket: WebSocket) -> None:
    await stream_agent(
        websocket=websocket,
        invoke_agent=invoke_admin_agent,
        admin_only=True,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app, host="127.0.0.1", port=8001)
