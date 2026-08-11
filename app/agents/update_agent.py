from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, SystemMessage
from langchain.agents.middleware import  ModelCallLimitMiddleware, HumanInTheLoopMiddleware, ToolCallLimitMiddleware
from langgraph.graph import END, StateGraph , START
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from typing import TypedDict
from pydantic import BaseModel
from enum import Enum
import asyncio
import uuid
from utils.prompt_loader import load_prompt
from utils.llm import get_llm
from utils.mcp_client import MCPTools
thread_id = str(uuid.uuid4())

llm = get_llm()

class AgentState(TypedDict):
    user_query : str
    table : list[str] | None = None
    schema : list
    query_result : str | None = None
    retry_feedback : str | None = None
    Insufficient_data : str | None = None 
    retry_count : int 
    Intent : str

class QueryIntent(str, Enum):
    UPDATE = 'UPDATE'
    DELETE = 'DELETE'
    UNKNOWN = 'UNKNOWN'
   
class TableOutput(BaseModel):
    table : list[str]
    Intent : QueryIntent

class QueryOutput(BaseModel):
    query_result : str | None = None
    retry_feedback : str | None = None
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
        return {
            "table" : response.table,
            "Intent" : response.Intent,
            "retry_feedback": ""
        }
    
    except Exception as e:
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
        res = (await get_columns_tool.ainvoke({"name" : state.get("table")}))[0].get("text")
        return {"schema" : res}
    
    except Exception as e:
        return f"error:{str(e)}"
    

async def risk_analyzer(query):
    count_rows_tool = next(
                    (tool for tool in tool_list if tool.name == "count_rows"),
                    None
                )
        
    if count_rows_tool is None:
            return "count_rows MCP tool not found"
    try:
        review_context = await count_rows_tool.ainvoke(query) 
        return review_context
    
    except Exception as e:
        print(f"Error: {e}")
        raise


config = {"configurable": {"thread_id": thread_id}}
allowed_tool = "run_db_query"
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
    
    schema = {"table": state.get("table"), "columns" : state.get("schema")} 
    human_msg = HumanMessage(content=f"""
                             user_query : {state.get("user_query")},
                             schema : {schema}
                             """
                            )
    
    system_prompt = Intents[state.get("Intent")] if state.get("Intent") != 'UNKNOWN' else ""
    try:
        response = await agent.ainvoke(
            {
                "messages":[system_prompt, human_msg]
            },
            config = config,
            version= "v2" 
        )

        # CASE 1: No tool call → directly return response
        if not response.interrupts:
            structured = response.value.get("structured_response")

            return {
                "query_result": str(structured.query_result) if structured else None,
                "retry_feedback": structured.retry_feedback if structured else None,
                "Insufficient_data": str(structured.Insufficient_data) if structured else None,
                "retry_count" : state.get("retry_count", 0) + 1
            }
        
         # CASE 2: Tool call → HITL flow
       
        print("="*100)
        Tool_info = response.interrupts[0].value['action_requests'][0]
        print("Tool_action", Tool_info['description'])
        risk = await risk_analyzer(Tool_info['args'])
        print("Approximately,", risk[0]['text'])
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
                    "message":  f"HUMAN REVIEW RESPONSE: {msg}"
                })

            elif user_input == "reject":
                msg = input("Enter rejection reason: ")
                decisions.append({
                    "type": "reject",
                    "action_name": action["name"],
                    "message": f"HUMAN REVIEW REJECTED: {msg}"
                })

            elif user_input == "edit":
                
                original_args = action["args"].copy()

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
                                "args": updated_data
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
        
        #print("="*100)
        #print("resumed_response:", resumed_response.value)
        structured = resumed_response.value.get("structured_response")
        #print("="*100)
        #print(structured)
        return {
            "query_result" : str(structured.query_result) if structured else None,
            "retry_feedback" : structured.retry_feedback if structured else None,
            "Insufficient_data" : str(structured.Insufficient_data) if structured else None,
            "retry_count" : state.get("retry_count", 0) + 1
        }
    
    except Exception as e:
        return {"call_limit" : str(e)}

# Conditional Edges
MAX_RETRY = 2
def route_after_final(state: AgentState):
    if state.get("retry_feedback") and state.get("retry_count", 0) < MAX_RETRY:
        return "retry"
    
    return "end"


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
        "end" : END
    }
)

update_graph = graph.compile()

async def invoke_update_delete_agent(user_query : str):
   
    input_msg = {"user_query" : user_query}
    response = await update_graph.ainvoke(input_msg)    
    return {
        "query_result" : response.get("query_result", None),
        "retry_feedback" : response.get("retry_feedback", None),
        "Insufficient_data" : response.get("Insufficient_data")
    }
