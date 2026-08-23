from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import SystemMessage
from langchain.agents.middleware import ToolCallLimitMiddleware
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

agent = create_agent(name="main_agent",
                     model=llm,
                     tools=[read_db, delete_db_data, update_db_data, write_db_data],
                     middleware=[tool_call_limit]
                    )


system_prompt = SystemMessage(content="You are helpful Database Assistant. Use attahced tools when you need answeer query. Your task is read the user query carefully and pass to tool in simple and clean natural langauge")

async def invoke_main_agent(user_query : str):
    
    stream = agent.astream_events(
        {
            "messages" : [system_prompt, user_query]
        },
        version="v2"
    )

    return stream


