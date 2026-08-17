from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
from langchain.agents.middleware import ToolCallLimitMiddleware
import asyncio
from agents.read_agent import invoke_read_agent
from agents.update_agent import invoke_update_delete_agent
from agents.write_agent import invoke_write_agent
from utils.llm import get_llm


llm = get_llm(streaming=True)

@tool
async def read_db(user_query : str):
    ''' Use this Tool for fetching data from database.
        Takes input in natural language as string
    '''
    response = await invoke_read_agent(user_query= user_query)
    return response


@tool
async def delete_db_data(user_query : str):
    ''' Use this Tool for deleting data records from database.
        Takes input in natural language as string
    '''
    response = await invoke_update_delete_agent(user_query=user_query)
    return response


@tool
async def update_db_data(user_query : str):
    ''' Use this Tool updating data records in the database.
        Takes input in natural language as string
    '''
    response = await invoke_update_delete_agent(user_query=user_query)
    return response


@tool
async def write_db_data(user_query : str):
    ''' Use this Tool adding new data records in the database.
        Takes input in natural language as string
    '''
    response = await invoke_write_agent(user_query)
    return response

tool_call_limit=ToolCallLimitMiddleware(run_limit=2, exit_behavior='end')
agent = create_agent(model=llm,
                     tools=[read_db, delete_db_data, update_db_data, write_db_data],
                     middleware=[tool_call_limit]
                    )

#usr_msg = "Donald Trump joined our organization on 25/5/2026.his birthdate is 19/12/2000. employee number is 500027, he will work as Senior Tester(title). Add his details in database."
#usr_msg = "Return the total number of emplpoyee who' birthday comes in first 5 days of June."
system_prompt = SystemMessage(content="You are helpful Database Assistant. Use attahced tools when you need answeer query. Your task is read the user query carefully and pass to tool in simple and clean natural langauge")
#human_msg = HumanMessage(content= usr_msg)

events = {
    "read_db" : "Agent working",
    "delete_db_data" : "Agent working..",
    "update_db_data" : "Agent working..",
    "write_db_data" : "Agent working..",
    "get_tables" : "Selecting source..",
    "get_columns" : "fetching schema..",
    "direct_execute_query" : "fethcing data from source.."
}

async def main():
    print("Database Assistant Started!")    
    print("Type 'exit' or 'quit' to stop.\n")

    while True:
        usr_msg = input("\nYou: ")

        if usr_msg.lower() in ["exit", "quit"]:
            print("Bot: Goodbye!")
            break
        
        print("Bot: ")

        stream = agent.astream_events(
            {
                "messages" : [system_prompt, usr_msg]
            },
            version="v2"
        )

        async for event in stream:
            if event["event"] == "on_tool_start":
                print(events.get(event["name"]))

            if event["event"] == "on_tool_end":
                print("\033[A\033[K", end="")

            if event["event"] == "on_chat_model_stream" and event["data"]["chunk"].content:
                print(event["data"]["chunk"].content, end="", flush=True)

     
 
if __name__ == "__main__":
    asyncio.run(main())