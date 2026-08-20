import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))
from langchain.agents import create_agent
from langchain.agents.middleware import ToolCallLimitMiddleware, ModelCallLimitMiddleware
from langchain.messages import SystemMessage, AIMessage
from utils.prompt_loader import load_prompt 
from utils.llm import get_llm
from urllib.parse import unquote_plus
from dotenv import load_dotenv
from utils.mcp_client import MCPTools
import json
import boto3
import os
import asyncio

load_dotenv()
llm = get_llm()

sqs = boto3.client('sqs', region_name="us-east-1")
s3 = boto3.client('s3')

SYSTEM_PROMPT = SystemMessage(content= load_prompt("event_driven_agent.txt"))
tools = asyncio.run(MCPTools.admin_tools()) 

# Middlewares
tool_call_limit = ToolCallLimitMiddleware(run_limit=4, exit_behavior="error")
model_call_limit = ModelCallLimitMiddleware(run_limit=5, exit_behavior="end")

agent = create_agent(model=llm, 
                     system_prompt=SYSTEM_PROMPT,
                     tools=tools,
                     middleware=[tool_call_limit, model_call_limit]
                    )

async def call_agent(report):
    response = await agent.ainvoke(
                    {"messages" : [{"role":"user", "content" : f"context: {json.dumps(report, indent=2)}"}]}
                )
    
    ai_messages = [m for m in response.get('messages') if isinstance(m, AIMessage)]
    if ai_messages:
        return f"Bot: {ai_messages[-1].content}\n"


while True:
    response = sqs.receive_message(
        QueueUrl = os.getenv("QUEUE_URL"),
        MaxNumberOfMessages=1,
        WaitTimeSeconds=20
    )

    messages = response.get("Messages", [])
    if messages:
        for msg in messages:
            try:
                body = json.loads(msg['Body'])
                record = body["Records"][0]
                bucket = record["s3"]["bucket"]["name"]
                key = unquote_plus(record["s3"]["object"]["key"])

                local_file =  "/tmp/report.json"
                s3.download_file(bucket,key,local_file)

                with open(local_file, "r") as file:
                    report = json.load(file)
                    print(report)


                print(f"{"="*30} AI Response {"="*30}")
                res = asyncio.run(call_agent(report))
                print(res)
                
                sqs.delete_message(QueueUrl=os.getenv("QUEUE_URL"),
                                    ReceiptHandle=msg["ReceiptHandle"]
                                )
                
                print("message deleted from queue")
            except Exception as e:
                print("error:", str(e))
                            
    else:
        print("Message Not available")
        continue