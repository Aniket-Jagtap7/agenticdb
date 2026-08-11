from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, ToolMessage, SystemMessage
from langchain.agents.middleware import wrap_tool_call, ModelCallLimitMiddleware, HumanInTheLoopMiddleware
from langchain.tools.tool_node import ToolCallRequest
from langgraph.graph import END, StateGraph , START
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from collections.abc import Callable
from typing import TypedDict
from pydantic import BaseModel, ValidationError
import asyncio
import uuid
from utils.prompt_loader import load_prompt 
from utils.llm import get_llm
from utils.mcp_client import MCPTools

thread_id = str(uuid.uuid4())

llm = get_llm()

class AgentState(TypedDict):
    user_query : str
    tool : list[str]
    tool_schema : list
    query_result : str | None = None
    retry_feedback : str | None = None
    Insufficient_data : str | None = None
    call_limit : str | None = None

class Tool_Node_Output(BaseModel):
    tool : list[str]

class QueryOutput(BaseModel):
    query_result : str | None = None
    retry_feedback : str | None = None
    Insufficient_data : str | None = None


tool_list = asyncio.run(MCPTools.write_tools())
tools = [{"tool_name" : tool.name, "description" : tool.description} for tool in tool_list]

SYSTEM_PROMPT = SystemMessage(content= load_prompt("write_table_selector.txt"))

async def select_tool_node(state : AgentState):

    human_msg = HumanMessage(content=f"""
                             User_query : {state.get("user_query")},
                             tools : {tools}
                             """
                            )
    msg = [SYSTEM_PROMPT, human_msg]
    model = llm.with_structured_output(Tool_Node_Output)

    try:
        response = await model.ainvoke(msg)
        return {"tool" : response.tool}
    
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
config = {"configurable": {"thread_id": thread_id}}
system_prompt = SystemMessage(content= load_prompt("write_agent.txt"))

async def  final_node(state : AgentState):
   
    tool = [tool for tool in tool_list if tool.name in state.get("tool")]
    
    # human in the loop middleware
    human_in_loop = HumanInTheLoopMiddleware(interrupt_on= {f"{tool_name}" : True for tool_name in state.get("tool")})
    
    agent = create_agent(model=llm, 
                         tools=tool, 
                         response_format=QueryOutput, 
                         middleware=[tool_error_handler, model_call_limit, human_in_loop],
                         checkpointer=InMemorySaver()
                        )
   
    human_msg = HumanMessage(content=f"user_query : {state.get("user_query")}")
    try:
        response = await agent.ainvoke(
            {
                "messages":[ system_prompt, human_msg]
            },
            config=config,
            version="v2",
        )
        
        # CASE 1: No tool call → directly return response
        if not response.interrupts:
            structured = response.value.get("structured_response")

            return {
                "query_result": str(structured.query_result) if structured else None,
                "retry_feedback": structured.retry_feedback if structured else None,
                "Insufficient_data": str(structured.Insufficient_data) if structured else None
            }
        
        # CASE 2: Tool call → HITL flow
        print("Interrupt Message:",response.interrupts)
        decision = ['approve', 'edit', 'respond', 'reject']
        while True:
            user_input = input(" Enter Decision (approve/edit/respond/reject): ").strip().lower()
            if user_input in decision:
                break
            else:
                print("provide correct input!!!")

        interrupt = response.interrupts[0].value
        decisions = []

        for action in interrupt["action_requests"]:

            if user_input == "respond":
                msg = input("Enter response message: ")
                decisions.append({
                    "type": "respond",
                    "action_name": action["name"],
                    "message": msg
                })

            elif user_input == "reject":
                msg = input("Enter rejection reason: ")
                decisions.append({
                    "type": "reject",
                    "action_name": action["name"],
                    "message": msg
                })

            elif user_input == "edit":
                original_args = action["args"]["data"].copy()

                print("Original Data:", original_args)
                print("Enter fields to update (leave blank to keep same)")

                updated_data = {}

                for key, value in original_args.items():
                    new_val = input(f"{key} ({value}): ").strip()

                    if new_val:
                        updated_data[key] = new_val
                    else:
                        updated_data[key] = value  

                decisions.append({
                    "type": "edit",
                    "action_name": action["name"],
                    "edited_action":{
                        "name": action["name"],
                        "args": {
                            "data": updated_data
                        }
                    }
                })

            else:  
                decisions.append({
                    "type": "approve",
                    "action_name": action["name"]
                })

        resumed_response = await agent.ainvoke(
            Command(
                resume = {"decisions": decisions},
            ),
            config=config,
            version="v2",
        )
        
        #structured = response.get("structured_response", {})
        #print("="*100)
        #print("resumed_response:", resumed_response)
        structured = resumed_response.value.get("structured_response")
        #print("="*100)
        #print(structured)
        return {
            "query_result" : str(structured.query_result) if structured else None,
            "retry_feedback" : structured.retry_feedback if structured else None,
            "Insufficient_data" : str(structured.Insufficient_data) if structured else None
        }
    
    except Exception as e:
        return {"call_limit" : str(e)}
    

graph = StateGraph(AgentState)
# Add nodes
graph.add_node("select_tool_node", select_tool_node)
graph.add_node("final_node", final_node)

# Add Edges
graph.add_edge(START, "select_tool_node")
graph.add_edge("select_tool_node", "final_node")
graph.add_edge("final_node", END)

write_graph = graph.compile()

async def invoke_write_agent(user_query : str):
    input_msg = {"user_query" : user_query}
    response = await write_graph.ainvoke(input_msg)    
    return {
        "query_result" : response.get("query_result", None),
        "retry_feedback" : response.get("retry_feedback", None),
        "Insufficient_data" : response.get("Insufficient_data")
    }



