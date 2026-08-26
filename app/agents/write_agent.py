from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, ToolMessage, SystemMessage
from langchain.agents.middleware import wrap_tool_call, ModelCallLimitMiddleware, HumanInTheLoopMiddleware
from langchain.tools.tool_node import ToolCallRequest
from langgraph.graph import END, StateGraph , START
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command, interrupt
from collections.abc import Callable
from typing import TypedDict, Annotated
from operator import add
from pydantic import BaseModel, ValidationError
import asyncio
import uuid
from utils.prompt_loader import load_prompt 
from utils.llm import get_llm
from utils.mcp_client import MCPTools
from utils.hitl_context import request_human_input
from utils.tool_decisions import build_tool_decisions

# config ID's for interrupts
thread_id = str(uuid.uuid4())
agent_config = {"configurable": {"thread_id": f"agent_{thread_id}"}}
graph_config = {"configurable" : {"thread_id": f"graph_{thread_id}"}}

# Iniatialization LLM
llm = get_llm()

class AgentState(TypedDict):
    user_query : str
    tool : list[str]
    tool_schema : list
    query_result : str | None = None
    no_schema_match : str | None = None
    Insufficient_data : str | None = None
    retry_count : int
    revised_input : Annotated[list[str], add]

class Tool_Node_Output(BaseModel):
    tool : list[str]

class QueryOutput(BaseModel):
    query_result : str | None = None
    no_schema_match : str | None = None
    Insufficient_data : str | None = None


tool_list = asyncio.run(MCPTools.write_tools())

tables = [{
        "table_name" : tool.name, 
        "columns" : list(tool.args_schema["properties"]["data"]["properties"].keys())
    } 
    for tool in tool_list
]

SYSTEM_PROMPT = SystemMessage(content= load_prompt("write_table_selector.txt"))


async def select_tool_node(state : AgentState):

    human_msg = HumanMessage(content=f"""
                             User_query : {state.get("user_query")},
                             tables : {tables}
                             """
                            )
    msg = [SYSTEM_PROMPT, human_msg]
    model = llm.with_structured_output(Tool_Node_Output)

    try:
        response = await model.ainvoke(msg)
        return {
            "tool" : response.tool,
            "retry_count" : state.get("retry_count", 0) + 1
        }
    
    except Exception as e:
        return  f"Error:{str(e)}"


# middleware for handling tool errors
@wrap_tool_call
async def tool_error_handler(request : ToolCallRequest, handler : Callable[[ToolCallRequest], ToolMessage]):
    try:
        return await handler(request)

    except ValidationError as e:
        return ToolMessage(content=
            "INVALID_TOOL_INPUT\n" 
            f"Tool: {request.tool_call['name']}\n"
            f"Input: {request.tool_call['args']}\n"
            f"Error: {str(e)}\n"
            "Fix the input to match the expected schema and call the tool again.",
            tool_call_id=request.tool_call["id"]
        )

    except Exception as e:
        return ToolMessage(content =
            "TOOL_EXECUTION_ERROR\n"
            f"Tool: {request.tool_call['name']}\n"
            f"Error: {str(e)}\n",
            tool_call_id=request.tool_call["id"]
        )

# middleware for model call limit
model_call_limit = ModelCallLimitMiddleware(run_limit=3, exit_behavior="error")
agent_memory = InMemorySaver()
system_prompt = SystemMessage(content= load_prompt("write_agent.txt"))


async def  final_node(state : AgentState):
   
    tool = [tool for tool in tool_list if tool.name in state.get("tool")]
    
    # human in the loop middleware
    human_in_loop = HumanInTheLoopMiddleware(interrupt_on= {f"{tool_name}" : True for tool_name in state.get("tool")})
    
    agent = create_agent(model=llm, 
                         tools=tool, 
                         response_format=QueryOutput, 
                         middleware=[tool_error_handler, model_call_limit, human_in_loop],
                         checkpointer=agent_memory
                        )
    
    requested_info = f"requested_data:{state.get("revised_input")}" if state.get("revised_input") else ""
   
    human_msg = HumanMessage(content=f"""
                             user_query : {state.get("user_query")},
                             {requested_info}
                            """
                            )
    
    try:
        response = await agent.ainvoke(
            {
                "messages":[ system_prompt, human_msg]
            },
            config=agent_config,
            version="v2",
        )
        
        # CASE 1: No tool call → directly return response
        if not response.interrupts:
            structured = response.value.get("structured_response")

            return {
                "query_result": structured.query_result if structured else None,
                "no_schema_match": structured.no_schema_match if structured else None,
                "Insufficient_data": structured.Insufficient_data if structured else None,
            }
        
        # CASE 2: Tool call → HITL flow
        while response.interrupts:
            
            print(f"table {state.get("tool")} will be updated")
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
            
                review_actions.append(
                    {
                        "action_index": action_index,
                        "name": action_name,
                        "args": action_args,
                    }
                )
            print("review_actions:", review_actions)
            review_payload = {
                "type" : "tool_review",
                "title" : "Human Review Required",
                "message" : "Please review the following tool actions and provide your decision.",
                "table" : ", ".join(state.get("tool")),
                "actions" : review_actions
            }

            human_review = ( await request_human_input(review_payload))
            print("Human review decision:", human_review)
            
            decisions = build_tool_decisions(action_requests=action_requests, human_review=human_review)
            print("Tool decisions:", decisions)
        
            
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
        }
    
    except Exception as e:
        return {"error" : str(e)}
        

def request_info_node(state : AgentState):
   
    revised_input = interrupt(state["Insufficient_data"])
   
    return {
        "revised_input": [revised_input],
        "Insufficient_data" : ""
    }


MAX_RETRY = 2

def route_after_final_node(state: AgentState):
    # Query resolved -> End graph
    if state.get("query_result"):
        return "end"

    # Need more information from user
    if state.get("Insufficient_data"):
        return "request_info_node"

    # Retry with feedback
    if state.get("no_schema_match"):
        if state.get("retry_count", 0) < MAX_RETRY:
            return "select_tool_node"
        else:
            return "end"
        
    raise ValueError(
        f"No route matched:{state}"
    )
  
    
graph = StateGraph(AgentState)
# Add nodes
graph.add_node("select_tool_node", select_tool_node)
graph.add_node("final_node", final_node)
graph.add_node("request_info_node", request_info_node)

# Add Edges
graph.add_edge(START, "select_tool_node")
graph.add_edge("select_tool_node", "final_node")

# conditional routing after final node
graph.add_conditional_edges(
    "final_node",
    route_after_final_node,
    {
        "end" : END,
        "request_info_node" : "request_info_node",
        "select_tool_node": "select_tool_node",
    }
)

graph.add_edge("request_info_node", "final_node")

write_graph = graph.compile(checkpointer=InMemorySaver())


async def invoke_write_agent(user_query : str):
    input_msg = {"user_query" : user_query, "revised_input":[]}
    response = await write_graph.ainvoke(input_msg, config=graph_config, version="v2")
    
    if not response.interrupts:   
        return {
            "query_result" : response.value.get("query_result", None),
            "no_schema_match" : response.value.get("no_schema_match", None),
            "Insufficient_data" : response.value.get("Insufficient_data")
        } 
    
    while response.interrupts:
        print("="*100)
        graph_interrupts = response.interrupts[0].value
        print("Graph interrupts:", graph_interrupts)
        updated_input = await request_human_input(graph_interrupts)
        
        response = await write_graph.ainvoke(
            Command(resume= updated_input),
            config=graph_config,
            version="v2"
        )
     
    return {
        "query_result" : response.value.get("query_result", None),
        "no_schema_match" : response.value.get("no_schema_match", None),
        "Insufficient_data" : response.value.get("Insufficient_data")
    }


