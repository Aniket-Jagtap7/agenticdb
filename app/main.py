from agents.main_agent import invoke_main_agent
from agents.admin_agent import invoke_admin_agent
from fastapi import FastAPI, WebSocket, WebSocketDisconnect


app = FastAPI()

events = {
    "read_db" : "Agent working",
    "delete_db_data" : "Agent working..",
    "update_db_data" : "Agent working..",
    "write_db_data" : "Agent working..",
    "get_tables" : "Selecting source..",
    "get_columns" : "fetching schema..",
    "direct_execute_query" : "fethcing data from source..",
    "employees" : "Records adding",
    "salaries" : "Records adding",
    "departments" : "Records adding",
    "deparment_employees" : "Records adding",
    "titles" : "Records adding",
    "manager_of_departments" : "Records adding"
}



@app.websocket("/chat")
async def user_chat(websocket : WebSocket):
    
    await websocket.accept()

    try:
        await websocket.send_text("Database Assistant Started!")
        await websocket.send_text("Type 'exit' or 'quit' to stop.")
        
        while True:

            usr_msg = await websocket.receive_text()

            if usr_msg.lower() in ["exit", "quit"]:
                await websocket.send_text("Goodbye!")
                await websocket.close()
                return

            stream = await invoke_main_agent(usr_msg)

            async for event in stream:
                if event["event"] == "on_tool_start":
                    #await websocket.send_text(events.get(event["name"]))
                    #print(events.get(event["name"]))
                    ...

                if event["event"] == "on_tool_end":
                    #await websocket.send_text("\033[A\033[K")
                    #print("\033[A\033[K", end="")
                    ...

                if event["event"] == "on_chat_model_stream" and event["data"]["chunk"].content:
                    await websocket.send_text(event["data"]["chunk"].content)
                    print(event["data"]["chunk"].content, end="", flush=True)  
                
            await websocket.send_text("__END_RESPONSE__")

    except WebSocketDisconnect:
        print("client closed")

    except Exception as e:
        print("Error:",e)



@app.websocket("/admin")
async def admin_chat(websocket : WebSocket):

    await websocket.accept()

    try:
        await websocket.send_text("Database Assistant Started!")
        await websocket.send_text("Type 'exit' or 'quit' to stop.")
        
        while True:
       
            usr_msg = await websocket.receive_text()

            if usr_msg.lower() in ["exit", "quit"]:
                await websocket.send_text("Goodbye!")
                await websocket.close()
                return

            stream = await invoke_admin_agent(usr_msg)

            async for event in stream:
                if event["event"] == "on_tool_start":
                    #await websocket.send_text(events.get(event["name"]))
                    #print(events.get(event["name"]))
                    ...

                if event["event"] == "on_tool_end":
                    #await websocket.send_text("\033[A\033[K")
                    #print("\033[A\033[K", end="")
                    ...

                if event["event"] == "on_chat_model_stream" and event["data"]["chunk"].content:
                    await websocket.send_text(event["data"]["chunk"].content)
                    print(event["data"]["chunk"].content, end="", flush=True)  
                
            await websocket.send_text("__END_RESPONSE__")
            
    except WebSocketDisconnect:
        print("client closed")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8001)
 
    
