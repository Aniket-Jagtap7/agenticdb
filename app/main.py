import ast
import json
from typing import Any, Awaitable, Callable
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from agents.admin_agent import invoke_admin_agent
from agents.main_agent import invoke_main_agent
from utils.hitl_context import (reset_human_input_handler, set_human_input_handler)


app = FastAPI(title="Database AI Assistant")


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


AgentInvoker = Callable[[str], Awaitable[Any]]


def create_websocket_human_input_handler(websocket: WebSocket):
    """Create a HITL callback bound to the current WebSocket."""

    async def get_human_input(interrupt_value: Any) -> Any:
        await websocket.send_json(
            {
                "type": "interrupt",
                "value": interrupt_value,
            }
        )

        while True:
            frontend_message = await websocket.receive_json()
            message_type = frontend_message.get("type")

            if message_type == "resume":
                if "value" not in frontend_message:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": "The resume message must contain a value.",
                        }
                    )
                    continue

                return frontend_message["value"]

            if message_type == "exit":
                raise WebSocketDisconnect(code=1000)

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
        return None

    try:
        parsed_value = json.loads(text_value)
        if isinstance(parsed_value, dict):
            return parsed_value
    except json.JSONDecodeError:
        pass

    try:
        parsed_value = ast.literal_eval(text_value)
        if isinstance(parsed_value, dict):
            return parsed_value
    except (ValueError, SyntaxError):
        pass

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

    return {
        "message": str(structured_content.get("message", "The generated CSV file is ready.")),
        "file_name": str(file_name),
        "download_url": str(download_url),
    }


def normalize_chunk_content(content: Any) -> str:
    """Convert common model chunk content shapes into displayable text."""

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


async def stream_agent(websocket: WebSocket, invoke_agent: AgentInvoker,) -> None:

    await websocket.accept()
    get_human_input = create_websocket_human_input_handler(websocket)

    try:
        await websocket.send_json({"type": "connected", "message": "Database Assistant Started!"})

        while True:
            frontend_message = await websocket.receive_json()
            message_type = frontend_message.get("type")

            if message_type == "exit":
                await websocket.send_json({"type": "goodbye", "message": "Goodbye!"})
                await websocket.close(code=1000)
                return

            if message_type != "message":
                await websocket.send_json({"type": "error", "message": "Expected a user message."})
                continue

            user_message = str(frontend_message.get("content", "")).strip()

            if not user_message:
                await websocket.send_json({"type": "error", "message": "Message cannot be empty."})
                continue

            handler_token = set_human_input_handler(get_human_input)

            # Reset for every new user message. Files generated in another
            # turn will never be appended to the current response.
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
                print("Agent execution error:", agent_error)

                await websocket.send_json(
                    {"type": "error", "message": str(agent_error)})

            finally:
                reset_human_input_handler(handler_token)

    except WebSocketDisconnect:
        print("WebSocket client disconnected")

    except Exception as error:
        print("WebSocket error:", error)

        try:
            await websocket.send_json({"type": "error", "message": str(error)})
            
        except Exception:
            pass


@app.websocket("/chat")
async def user_chat(websocket: WebSocket) -> None:
    await stream_agent(
        websocket=websocket,
        invoke_agent=invoke_main_agent,
    )


@app.websocket("/admin")
async def admin_chat(websocket: WebSocket) -> None:
    await stream_agent(
        websocket=websocket,
        invoke_agent=invoke_admin_agent,
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app, host="127.0.0.1", port=8001)
