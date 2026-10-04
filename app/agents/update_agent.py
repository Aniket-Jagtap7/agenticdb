from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.agents.middleware import  ModelCallLimitMiddleware, HumanInTheLoopMiddleware, ToolCallLimitMiddleware
from langgraph.graph import END, StateGraph , START
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt
from typing import TypedDict, Annotated, Any, Awaitable, Callable
from operator import add
from pydantic import BaseModel
from enum import Enum
from utils.prompt_loader import load_prompt
from utils.llm import get_llm
from utils.mcp_client import MCPTools
from utils.hitl_context import request_human_input
from utils.tool_decisions import build_tool_decisions
from langchain.tools import tool
import asyncio
import uuid
import json
import logging

logger = logging.getLogger(__name__)

# config ID's for interrupts
thread_id = str(uuid.uuid4())
agent_config = {"configurable": {"thread_id": f"agent_{thread_id}"}}
graph_config = {"configurable" : {"thread_id": f"graph_{thread_id}"}}

HumanInputCallback = Callable[[Any],Awaitable[Any]]

# LLM initialization
llm = get_llm()

class AgentState(TypedDict):
    user_query : str
    table : list[str] | None = None
    schema : list
    query_result : str | None = None
    no_schema_match : str | None = None
    Insufficient_data : str | None = None 
    retry_count : int 
    Intent : str
    revised_input : Annotated[list[str], add]

class QueryIntent(str, Enum):
    UPDATE = 'UPDATE'
    DELETE = 'DELETE'
    UNKNOWN = 'UNKNOWN'
   
class TableOutput(BaseModel):
    table : list[str]
    Intent : QueryIntent

class QueryOutput(BaseModel):
    query_result : str | None = None
    no_schema_match : str | None = None
    Insufficient_data : str | None = None
    

tools = asyncio.run(MCPTools.read_tools())

get_tables_tool = next(
                    (tool for tool in tools if tool.name == "get_tables"),
                    None
                )

get_columns_tool = next(
                    (tool for tool in tools if tool.name == "get_columns"),
                    None
                )

SYSTEM_PROMPT = SystemMessage(content= load_prompt("update_table_selector.txt"))

async def select_table_node(state : AgentState):
    logger.info("selecting tables to build query")
    feedback = state.get("retry_feedback", "")    
    human_msg = HumanMessage(content=f"""
                             User_query : {state.get("user_query")},
                             Available Tables: {(await get_tables_tool.ainvoke({}))[0].get("text")}, 
                             Feedback: {feedback}"""
                            )
    
    msg = [SYSTEM_PROMPT , human_msg]
    model = llm.with_structured_output(TableOutput)
    try:
        response = await model.ainvoke(msg)
        logger.info("selected tables: %s, Intent: %s", response.table, response.Intent)
        return {
            "table" : response.table,
            "Intent" : response.Intent,
            "no_schema_match": ""
        }
    
    except Exception as e:
        logger.exception("table selector node failed")
        return f"Error:{str(e)}"


def unknown_intent_node(state : AgentState):
    return Command(
        update={
            "query_result": "Sorry, I couldn't understand your request."
        },
        goto=END
    )


async def get_table_schema(state: AgentState):
    try:
        logger.info("Fetching table schema..")
        res = (await get_columns_tool.ainvoke({"name" : state.get("table")}))[0].get("text")
        return {"schema" : res}
    
    except Exception as e:
        logger.exception("Table schema fetching failed")
        return f"error:{str(e)}"
    

async def risk_analyzer(query):
    logger.info("Analyzing a risk of query")
    count_rows_tool = next(
                    (tool for tool in tool_list if tool.name == "count_rows"),
                    None
                )
        
    if count_rows_tool is None:
            logger.warning("count_rows MCP tool not available")
            return "count_rows MCP tool not found"
    try:
        review_context = await count_rows_tool.ainvoke(query) 
        return review_context
    
    except Exception as e:
        logger.exception("risk analyzer failed")
        print(f"Error: {e}")
        raise


config = {"configurable": {"thread_id": thread_id}}
allowed_tool = "run_query"
tool_list = asyncio.run(MCPTools.update_tools())
tool = [tool for tool in tool_list if tool.name == allowed_tool]

# middlewares for model call and tool call limit, human in loop
human_in_loop = HumanInTheLoopMiddleware(interrupt_on= {f"{allowed_tool}" : True })
model_call_limit = ModelCallLimitMiddleware(run_limit=3, exit_behavior="error")
tool_call_limit = ToolCallLimitMiddleware(run_limit=2, exit_behavior="error")

agent = create_agent(model=llm, 
                     tools=tool, 
                     middleware=[model_call_limit, tool_call_limit, human_in_loop],
                     response_format= QueryOutput,
                     checkpointer= InMemorySaver()
                    )

Intents = {
    "UPDATE" : SystemMessage(content= load_prompt("update_agent.txt")),
    "DELETE" : SystemMessage(content= load_prompt("delete_agent.txt"))
}


async def final_node(state : AgentState):
    logger.info("Building SQL query for, %s", state.get("Intent"))
    schema = {"table": state.get("table"), "columns" : state.get("schema")} 
    requested_info = f"requested_data:{state.get("revised_input")}" if state.get("revised_input") else ""
    
    human_msg = HumanMessage(content=f"""
                             user_query : {state.get("user_query")},
                             schema : {schema},
                             {requested_info}
                             """
                            )
    
    system_prompt = Intents[state.get("Intent")] if state.get("Intent") != 'UNKNOWN' else ""
    try:
        response = await agent.ainvoke(
            {
                "messages":[system_prompt, human_msg]
            },
            config = agent_config,
            version= "v2" 
        )
      
        # CASE 1: No tool call → directly return response
        if not response.interrupts:
            structured = response.value.get("structured_response")

            return {
                "query_result": structured.query_result if structured else None,
                "no_schema_match": structured.no_schema_match if structured else None,
                "Insufficient_data": structured.Insufficient_data if structured else None,
                "retry_count" : state.get("retry_count", 0) + 1
            }
        
         # CASE 2: Tool call → HITL flow
        while response.interrupts:
            logger.info("Waiting for Human decision..")
            logger.info("%s table will be updated", state.get("table"))
            interrupt_value = response.interrupts[0].value
            action_requests = interrupt_value.get("action_requests", [])
            if not action_requests:
                raise ValueError(
                    "Tool-review interrupt does not contain any action requests."
                )
            
            review_actions = []

            for action_index, action in enumerate(action_requests):
                action_name = action.get("name", "unknown tool")
                action_args = action.get("args", {})
                default_risk_message = ("Risk analysis unavailable.")
                risk_message = default_risk_message

                try:
                    risk_result = await risk_analyzer(action_args)
                    if risk_result:
                        first_risk = risk_result[0]
                        if isinstance(first_risk, dict):
                            risk_message = first_risk.get("text", default_risk_message)

                except Exception:
                    risk_message = default_risk_message
                
                review_actions.append(
                    {
                        "action_index": action_index,
                        "name": action_name,
                        "args": action_args,
                        "risk_analysis": risk_message
                    }
                )

            review_payload = {
                "type" : "tool_review",
                "title" : "Human Review Required",
                "message" : "Please review the following tool actions and provide your decision.",
                "table" : state.get("table"),
                "actions" : review_actions
            }

            human_review = ( await request_human_input(review_payload))
            logger.info("Human review decision: %s", human_review)
            
            decisions = build_tool_decisions(action_requests=action_requests, human_review=human_review)
            logger.info("Tool decisions: %s", decisions)
        
            response = await agent.ainvoke(
                Command(
                    resume = {"decisions": decisions},
                ),
                config=agent_config,
                version="v2",
            )
            
        structured = response.value.get("structured_response")
    
        return {
            "query_result" : structured.query_result if structured else None,
            "no_schema_match" : structured.no_schema_match if structured else None,
            "Insufficient_data" : structured.Insufficient_data if structured else None,
            "retry_count" : state.get("retry_count", 0) + 1
        }
    
    except Exception as e:
        logger.exception("SQL query build and execute failed")
        return {"Error" : str(e)}


def request_info_node(state : AgentState):
    logger.info("Requesting additional information")
    revised_input = interrupt(state["Insufficient_data"])
    
    return {
        "revised_input": [revised_input],
        "Insufficient_data" : ""
    }


# Conditional Edges
MAX_RETRY = 2
def route_after_final(state: AgentState):
    if state.get("no_schema_match"):
        if state.get("retry_count", 0) < MAX_RETRY:
            return "retry"
        else:
            return "end"
    
    # Query resolved -> End graph
    if state.get("query_result"):
        return "end"
    
    # Need more information from user
    if state.get("Insufficient_data"):
        return "request_info_node"

    raise ValueError(
         f"No route matched:{state}"
    )


def route_after_select_table(state : AgentState):
    if state.get("Intent") == "UNKNOWN":
        return "unknown_intent_node"

    return "get_table_schema"


graph = StateGraph(AgentState)

# Adding nodes to the graph
graph.add_node("select_table_node", select_table_node)
graph.add_node("unknown_intent_node", unknown_intent_node)
graph.add_node("get_table_schema",get_table_schema)
graph.add_node("final_node", final_node)
graph.add_node("request_info_node", request_info_node)

# Adding Edges
graph.add_edge(START, "select_table_node")
graph.add_conditional_edges(
    "select_table_node",
    route_after_select_table,
    {
        "unknown_intent_node": "unknown_intent_node",
        "get_table_schema": "get_table_schema"
    }
)
graph.add_edge("get_table_schema","final_node")
graph.add_conditional_edges(
    "final_node",
    route_after_final,
    {
        "retry" : "select_table_node",
        "request_info_node" : "request_info_node",
        "end" : END
    }
)

graph.add_edge("request_info_node", "final_node") 

update_graph = graph.compile(checkpointer=InMemorySaver())

async def invoke_update_delete_agent(user_query : str):
    logger.info("Executing sub-agent")
    input_msg = {"user_query" : user_query}
    response = await update_graph.ainvoke(input_msg, config=graph_config, version="v2") 
   
    if not response.interrupts:
        return {
            "query_result" : response.value.get("query_result", None),
            "no_schema_match" : response.value.get("no_schema_match", None),
            "Insufficient_data" : response.value.get("Insufficient_data")
        }
    
    while response.interrupts:
        graph_interrupts = response.interrupts[0].value
        updated_input = await request_human_input(graph_interrupts)
        response = await update_graph.ainvoke(
            Command(resume= updated_input),
            config=graph_config,
            version="v2"
        )
        
    logger.info("sub-agent execution completed.")
    return {
        "query_result" : response.value.get("query_result", None),
        "no_schema_match" : response.value.get("no_schema_match", None),
        "Insufficient_data" : response.value.get("Insufficient_data")
    }



