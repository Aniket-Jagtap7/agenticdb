from agents.main_agent import invoke_main_agent
from agents.admin_agent import invoke_admin_agent
from fastapi import FastAPI, WebSocket, WebSocketDisconnect

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


async def stream_agent(websocket: WebSocket, invoke_agent):
    await websocket.accept()
    try:
        await websocket.send_text("Database Assistant Started!")
        await websocket.send_text("Type 'exit' or 'quit' to stop.")

        while True:
            user_message = await websocket.receive_text()

            if user_message.strip().lower() in {"exit", "quit"}:
                await websocket.send_text("Goodbye!")
                await websocket.close(code=1000)
                return

            stream = await invoke_agent(user_message)
            async for event in stream:
                event_type = event.get("event")

                if event_type == "on_tool_start":
                    tool_name = event.get("name", "")
                    status_message = EVENTS.get(tool_name)
                    if status_message:
                        await websocket.send_text(f"__STATUS__:{status_message}")

                elif event_type == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    content = getattr(chunk, "content", "")
                    if content:
                        await websocket.send_text(content)

            await websocket.send_text(END_RESPONSE)

    except WebSocketDisconnect:
        print("Client disconnected")
    except Exception as exc:
        print(f"WebSocket error: {exc}")
        try:
            await websocket.send_text(f"__ERROR__:{str(exc)}")
            await websocket.send_text(END_RESPONSE)
            await websocket.close(code=1011)
        except Exception:
            pass


@app.websocket("/chat")
async def user_chat(websocket: WebSocket):
    await stream_agent(websocket, invoke_main_agent)


@app.websocket("/admin")
async def admin_chat(websocket: WebSocket):
    await stream_agent(websocket, invoke_admin_agent)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
