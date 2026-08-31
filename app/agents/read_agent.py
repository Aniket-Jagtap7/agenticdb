from langchain.agents import create_agent
from langchain.tools import tool
from langgraph.graph import END, StateGraph , START
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from typing import TypedDict
from pydantic import BaseModel
from enum import Enum
import asyncio
from utils.prompt_loader import load_prompt 
from utils.llm import get_llm
from utils.mcp_client import MCPTools

llm = get_llm()

class Stautus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"

class AgentState(TypedDict):
    user_query : str
    table : list[str]
    schema : list
    query_result : str | None = None
    retry_feedback : str | None = None
    retry_count : int
    status : Stautus
    

class TableOutput(BaseModel):
    table : list[str]

tools = asyncio.run(MCPTools.read_tools())

get_tables_tool = next(
                    (tool for tool in tools if tool.name == "get_tables"),
                    None
                )

get_columns_tool = next(
                    (tool for tool in tools if tool.name == "get_columns"),
                    None
                )

SYSTEM_PROMPT = SystemMessage(content= load_prompt("read_table_selector.txt"))

async def select_table_node(state : AgentState):

    feedback = state.get("retry_feedback", "")
    human_msg = HumanMessage(content=f"""
                             User_query : {state.get("user_query")},
                             Available tables: {(await get_tables_tool.ainvoke({}))[0].get("text")},
                             Feedback: {feedback}
                            """
                            )
    msg = [SYSTEM_PROMPT , human_msg]
    model = llm.with_structured_output(TableOutput)

    try:
        response = await model.ainvoke(msg)
        return {
            "table" : response.table,
            "retry_feedback": ""
        }
    
    except Exception as e:
        return f"Error:{str(e)}"


async def get_table_schema(state: AgentState):
    try:
        res = (await get_columns_tool.ainvoke({"name" : state.get("table")}))[0].get("text")
        return {"schema" : res}
    
    except Exception as e:
        return f"error:{str(e)}"


class QueryOutput(BaseModel):
    query_result : str | None = None
    retry_feedback : str | None = None
    status : Stautus

# middleware for model call limit
model_call_limit = ModelCallLimitMiddleware(run_limit=3, exit_behavior="error")
tool_call_limit = ToolCallLimitMiddleware(run_limit=2, exit_behavior="error")

allowed_tool = "direct_execute_query"
tool = [tool for tool in tools if tool.name == allowed_tool]

agent = create_agent(model=llm,
                     tools=tool, 
                     middleware=[model_call_limit],
                     response_format= QueryOutput
                    )

system_prompt = SystemMessage(content= load_prompt("read_agent.txt"))

async def final_node(state : AgentState):
      
    schema = {"table": state.get("table"), "columns" : state.get("schema")} 
    human_msg = HumanMessage(content=f"""
                             user_query : {state.get("user_query")},
                             schema : {schema}
                             """
                            )
    try:
        response = await agent.ainvoke(
            {
            "messages":[system_prompt, human_msg]
            }
        )

        structured = response.get("structured_response", {})
        return {
            "query_result": str(structured.query_result) or None,
            "retry_feedback" : structured.retry_feedback or None,
            "status" : structured.status or None,
            "retry_count" : state.get("retry_count", 0) + 1
        }
    
    except Exception as e:
        return {"call_limit" : str(e)}

MAX_RETRY = 2
def route_after_final(state: AgentState):
    if state.get("retry_feedback") and state.get("retry_count", 0) < MAX_RETRY:
        return "retry"
    
    return "end"

graph = StateGraph(AgentState)

# Adding nodes to the graph
graph.add_node("select_table_node", select_table_node)
graph.add_node("get_table_schema",get_table_schema)
graph.add_node("final_node", final_node)

# Adding Edges
graph.add_edge(START, "select_table_node")
graph.add_edge("select_table_node","get_table_schema")
graph.add_edge("get_table_schema","final_node")
graph.add_conditional_edges(
    "final_node",
    route_after_final,
    {
        "retry" : "select_table_node",
        "end" : END
    }
)

read_graph = graph.compile()


async def invoke_read_agent(user_query : str):
   
    input_msg = {"user_query" : user_query}
    response = await read_graph.ainvoke(input_msg)    
    return {
        "query_result" : response.get("query_result", None),
        "retry_feedback" : response.get("retry_feedback", None)
    }
    


    
    