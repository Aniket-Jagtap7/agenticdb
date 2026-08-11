from langchain.agents import create_agent
from langchain.tools import tool
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import asyncio
from Agents.read_agent import invoke_read_agent
from Agents.update_agent import invoke_update_delete_agent
from Agents.write_agent import invoke_write_agent
from utils.llm import get_llm


llm = get_llm()

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


agent = create_agent(model=llm,
                     tools=[read_db, delete_db_data, update_db_data, write_db_data]
                    )

#usr_msg = "Donald Trump joined our organization on 25/5/2026.his birthdate is 19/12/2000. employee number is 500012, he will contribute in our organization as a Senior Tester. Add his details in database."
#usr_msg = "Return the total number of emplpoyee who' birthday comes in first 5 days of June."
system_prompt = SystemMessage(content="You are helpful Database Assistant. Use attahced tools when you need answeer query. Your task is read the user query carefully and pass to tool in simple and clean natural langauge")
#human_msg = HumanMessage(content= usr_msg)

async def main():
    print("Database Assistant Started!")    
    print("Type 'exit' or 'quit' to stop.\n")

    while True:
        usr_msg = input("You: ")
        if usr_msg.lower() in ["exit", "quit"]:
            print("Bot: Goodbye!")
            break
        response = await agent.ainvoke(
            {
                'messages' : [system_prompt, HumanMessage(content=usr_msg)]
            }
        )
        #print(response.get('messages'))
        ai_messages = [m for m in response.get('messages') if isinstance(m, AIMessage)]
        if ai_messages:
            print(f"Bot: {ai_messages[-1].content}\n")
        else:
            print("Bot: No response received.\n")
 
if __name__ == "__main__":
    asyncio.run(main())