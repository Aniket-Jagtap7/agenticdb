from langchain.agents import create_agent
from langchain.messages import  HumanMessage,  SystemMessage, AIMessage
from langchain.agents.middleware import ToolCallLimitMiddleware
from langchain.tools import tool
from utils.llm import get_llm
from utils.mcp_client import MCPTools
from utils.prompt_loader import load_prompt
import asyncio


llm = get_llm(streaming=True)

tool = asyncio.run(MCPTools.admin_tools())

tool_call_limit=ToolCallLimitMiddleware(run_limit=2, exit_behavior='end')

agent = create_agent(
    name="admin_agent",
    model=llm,
    tools=tool,
    middleware=[tool_call_limit],
)


async def event_driven_admin_agent(report):
    
    system_prompt = SystemMessage(content= load_prompt("event_driven_agent.txt"))
    usr_msg = HumanMessage(content=f"context:{report}")

    response = await agent.ainvoke(
        {"messages":[system_prompt, usr_msg]}
    )

    ai_messages = [m for m in response.get('messages') if isinstance(m, AIMessage)]
    if ai_messages:
        return f"Bot:{ai_messages[-1].content}\n"



async def invoke_admin_agent(user_query : str):
   
    system_prompt= SystemMessage(content= load_prompt("admin_agent.txt"))
    usr_msg = HumanMessage(content= user_query)
    
    stream = agent.astream_events(
        {
            "messages" : [system_prompt, usr_msg]
        }
    )

    return stream 


