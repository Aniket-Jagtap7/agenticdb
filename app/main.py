from agents.main_agent import invoke_main_agent
from agents.admin_agent import invoke_admin_agent
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Any
from utils.hitl_context import reset_human_input_handler, set_human_input_handler
import uuid



app = FastAPI(title="Database AI Assistant")

END_RESPONSE = "__END_RESPONSE__"

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


def create_websocket_human_input_handler(
    websocket: WebSocket,
):
    async def get_human_input(
        interrupt_value: Any,
    ) -> Any:
        """
        Send the graph interrupt to React and wait for
        the React popup response.
        """

        await websocket.send_json(
            {
                "type": "interrupt",
                "value": interrupt_value,
            }
        )

        while True:
            frontend_message = (
                await websocket.receive_json()
            )

            message_type = frontend_message.get(
                "type"
            )

            if message_type == "resume":
                if "value" not in frontend_message:
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": (
                                "The resume message must "
                                "contain a value."
                            ),
                        }
                    )

                    continue

                return frontend_message["value"]

            await websocket.send_json(
                {
                    "type": "error",
                    "message": (
                        "The graph is waiting for human "
                        "input. Please answer the popup."
                    ),
                }
            )

    return get_human_input

@app.websocket("/chat")
async def user_chat(
    websocket: WebSocket,
):
    await websocket.accept()

    get_human_input = (
        create_websocket_human_input_handler(
            websocket
        )
    )

    try:
        await websocket.send_json(
            {
                "type": "connected",
                "message": (
                    "Database Assistant Started!"
                ),
            }
        )

        while True:
            frontend_message = (
                await websocket.receive_json()
            )

            message_type = frontend_message.get(
                "type"
            )

            if message_type == "exit":
                await websocket.send_json(
                    {
                        "type": "goodbye",
                        "message": "Goodbye!",
                    }
                )

                await websocket.close(code=1000)
                return

            if message_type != "message":
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": (
                            "Expected a user message."
                        ),
                    }
                )

                continue

            user_message = str(
                frontend_message.get(
                    "content",
                    "",
                )
            ).strip()

            if not user_message:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": (
                            "Message cannot be empty."
                        ),
                    }
                )

                continue

            # Register the handler for this agent execution.
            handler_token = (
                set_human_input_handler(
                    get_human_input
                )
            )

            try:
                # invoke_main_agent remains unchanged.
                # It still receives only user_message.
                stream = await invoke_main_agent(
                    user_message
                )

                async for event in stream:
                    event_type = event.get("event")

                    if event_type == "on_tool_start":
                        tool_name = event.get(
                            "name",
                            ""
                        )

                        status_message = event.get(
                            tool_name
                        )

                        if status_message:
                            await websocket.send_json(
                                {
                                    "type": "status",
                                    "content": (
                                        status_message
                                    ),
                                }
                            )

                    elif (
                        event_type
                        == "on_chat_model_stream"
                    ):
                        chunk = (
                            event.get("data", {})
                            .get("chunk")
                        )

                        content = getattr(
                            chunk,
                            "content",
                            "",
                        )

                        if content:
                            await websocket.send_json(
                                {
                                    "type": "chunk",
                                    "content": content,
                                }
                            )

                await websocket.send_json(
                    {
                        "type": "complete",
                    }
                )

            finally:
                # Always remove the handler when this
                # agent execution finishes or fails.
                reset_human_input_handler(
                    handler_token
                )

    except WebSocketDisconnect:
        print("Client disconnected")

    except Exception as error:
        print(
            "WebSocket error:",
            error
        )

        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": str(error),
                }
            )
        except Exception:
            pass

'''
@app.websocket("/chat")
async def user_chat(websocket: WebSocket):
    await stream_agent(websocket, invoke_main_agent)


@app.websocket("/admin")
async def admin_chat(websocket: WebSocket):
    await stream_agent(websocket, invoke_admin_agent)

'''
@app.websocket("/admin")
async def admin_chat(
    websocket: WebSocket,
):
    await websocket.accept()

    # This callback sends interrupt data to React and waits
    # for the React popup response.
    get_human_input = (
        create_websocket_human_input_handler(
            websocket
        )
    )

    try:
        await websocket.send_json(
            {
                "type": "connected",
                "message": (
                    "Database Assistant Started!"
                ),
            }
        )

        while True:
            # Normal user messages are read here.
            frontend_message = (
                await websocket.receive_json()
            )

            message_type = frontend_message.get(
                "type"
            )

            # Close the WebSocket when React sends:
            # {"type": "exit"}
            if message_type == "exit":
                await websocket.send_json(
                    {
                        "type": "goodbye",
                        "message": "Goodbye!",
                    }
                )

                await websocket.close(code=1000)
                return

            # The outer loop only accepts normal messages.
            # Resume messages are handled inside the
            # HITL callback while the graph is interrupted.
            if message_type != "message":
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": (
                            "Expected a user message."
                        ),
                    }
                )

                continue

            user_message = str(
                frontend_message.get(
                    "content",
                    "",
                )
            ).strip()

            if not user_message:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": (
                            "Message cannot be empty."
                        ),
                    }
                )

                continue

            # Register the WebSocket HITL callback for
            # this specific admin-agent execution.
            handler_token = (
                set_human_input_handler(
                    get_human_input
                )
            )

            try:
                # Do not change this call.
                # Your admin agent still accepts only
                # the user message.
                stream = await invoke_admin_agent(
                    user_message
                )

                async for event in stream:
                    event_type = event.get(
                        "event"
                    )

                    if event_type == "on_tool_start":
                        tool_name = event.get(
                            "name",
                            "",
                        )

                        status_message = event.get(
                            tool_name
                        )

                        if status_message:
                            await websocket.send_json(
                                {
                                    "type": "status",
                                    "content": (
                                        status_message
                                    ),
                                }
                            )

                    elif (
                        event_type
                        == "on_chat_model_stream"
                    ):
                        chunk = (
                            event.get("data", {})
                            .get("chunk")
                        )

                        content = getattr(
                            chunk,
                            "content",
                            "",
                        )

                        if content:
                            await websocket.send_json(
                                {
                                    "type": "chunk",
                                    "content": content,
                                }
                            )

                # This is sent only after the agent stream
                # finishes, including all HITL interruptions.
                await websocket.send_json(
                    {
                        "type": "complete",
                    }
                )

            except WebSocketDisconnect:
                # Re-raise so the outer exception handler
                # can finish the endpoint cleanly.
                raise

            except Exception as agent_error:
                print(
                    "Admin agent execution error:",
                    agent_error,
                )

                await websocket.send_json(
                    {
                        "type": "error",
                        "message": str(
                            agent_error
                        ),
                    }
                )

            finally:
                # Always clear the ContextVar after this
                # admin-agent execution finishes or fails.
                reset_human_input_handler(
                    handler_token
                )

    except WebSocketDisconnect:
        print("Admin client disconnected")

    except Exception as error:
        print(
            "Admin WebSocket error:",
            error,
        )

        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": str(error),
                }
            )
        except Exception:
            # The WebSocket may already be closed.
            pass


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
