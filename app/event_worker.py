from urllib.parse import unquote_plus
import json
import boto3
import os
from agents.admin_agent import event_driven_admin_agent
import asyncio

sqs = boto3.client('sqs', region_name="us-east-1")
s3 = boto3.client('s3')


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
                    
                res = asyncio.run(event_driven_admin_agent(report))
                
                sqs.delete_message(QueueUrl=os.getenv("QUEUE_URL"),
                                    ReceiptHandle=msg["ReceiptHandle"]
                                )
                
                print("message deleted from queue")
            except Exception as e:
                print("error:", str(e))
                            
    else:
        print("Message Not available")
        continue