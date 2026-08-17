from langchain.agents import create_agent
from langchain.messages import SystemMessage, HumanMessage, AIMessage
from langchain.tools import tool
from langchain.agents.middleware import ToolCallLimitMiddleware
from utils.llm import get_llm
import asyncio 
import time 
from agents.read_agent import invoke_read_agent
from agents.write_agent import invoke_write_agent



@tool
async def read_db(user_query : str):
    ''' Use this Tool for fetching data from database.
        Takes input in natural language as string
    '''
    response = await invoke_read_agent(user_query= user_query)
    return response


@tool
async def write_db_data(user_query : str):
    ''' Use this Tool adding new data records in the database.
        Takes input in natural language as string
    '''
    response = await invoke_write_agent(user_query)
    return response

tool_call_limit = ToolCallLimitMiddleware(run_limit=2, exit_behavior='end')
agent = create_agent(model=get_llm(streaming=True),
                     tools=[read_db, write_db_data],
                     middleware=[tool_call_limit]
                    )


system_prompt = SystemMessage(content="You are helpful Database Assistant. Use attahced tools when you need answeer query. Your task is read the user query carefully and pass to tool in simple and clean natural langauge")
human_msg = HumanMessage(content="add one new record first_name:donald, last_name:trump, birth date:25/12/2000, joining date:12/12/2012, emp_no:500020")

events = {
    "read_db" : "Agent working",
    "delete_db_data" : "Agent working",
    "update_db_data" : "Agent working",
    "write_db_data" : "Agent working",
    "get_tables" : "Selecting source",
    "get_columns" : "fetching schema",
    "direct_execute_query" : "fethcing data from source",
    "employees" : "Records adding",
    "salaries" : "Records adding",
    "departments" : "Records adding",
    "deparment_employees" : "Records adding",
    "titles" : "Records adding",
    "manager_of_departments" : "Records adding"
}

async def main():
    
    stream = agent.astream_events(
        {
            "messages" : [system_prompt, human_msg]
        },
        version="v2"
    )

    async for event in stream:
        if event["event"] == "on_tool_start":
            print(events.get(event["name"]))

        if event["event"] == "on_tool_end":
            #print("\033[A\033[K", end="")
            ...

        if event["event"] == "on_chat_model_stream" and event["data"]["chunk"].content:
            print(event["data"]["chunk"].content, end="", flush=True)
           
        
            
        

    '''
    async for event in stream:
        if event["event"] == "on_chat_model_stream":
            print(event["data"]["chunk"].content, end="", flush=True)
    '''

asyncio.run(main())




# event streaming version v3
'''
    stream =await agent.astream_events(
        {
            "messages" : [system_prompt, human_msg] 
        },
        version="v3"
    )

    async for message in stream.messages:
        async for delta in message.text:
            print(delta, end="", flush=True)

'''