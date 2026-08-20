from fastmcp import FastMCP
from fastapi import APIRouter
from database.db import db
import boto3
import time
from utils.models import ResourceCheck
import smtplib
from email.mime.text import MIMEText
import os
from dotenv import load_dotenv

load_dotenv()

ssm = boto3.client('ssm', region_name="us-east-1")
CPU_CORE = 2

# create MCP server
mcp = FastMCP("admin_tools")
mcp_admin = mcp.http_app(path="/")


async def check_resource_usage(query_id : ResourceCheck):
    
    if len(query_id) == 1:
        query = """    
        SELECT        
           t.THREAD_OS_ID,
           t.THREAD_ID,
           t.PROCESSLIST_ID,
           m.current_allocated
        FROM performance_schema.threads t
        JOIN sys.memory_by_thread_by_current_bytes m
            ON t.THREAD_ID = m.thread_id
        WHERE PROCESSLIST_ID = %s  AND t.PROCESSLIST_INFO IS NOT NULL  
        """

        params = (query_id[0],)

    else:
        placeholders = ",".join(["%s"] * len(query_id))
        query = f"""
            SELECT 
                t.THREAD_OS_ID,
                t.THREAD_ID,
                t.PROCESSLIST_ID,
                m.current_allocated
            FROM 
                performance_schema.threads t
            JOIN sys.memory_by_thread_by_current_bytes m
                ON t.THREAD_ID = m.thread_id
            WHERE 
                PROCESSLIST_ID IN ({placeholders}) AND t.PROCESSLIST_INFO IS NOT NULL;
        """
        params = query_id

    res = await db.run_admin_query(query, params)
    #print(res)
    if len(res) == 0:
        return "Empty set, Data is not available for provided, processlist id.."
    return res


@mcp.tool()
async def check_resource_usage_by_queries(query_id : tuple):
    '''
        Use this tool, to see how much CPU and memory slow queries, or long-running queries consuming.
        Requires input parameter: running query id's as a tuple(int)
    '''
    
    res = await check_resource_usage(query_id=query_id)
    
    if type(res) != list:
        return res
  
    Thread_os_id =  [id['THREAD_OS_ID'] for id in res]
    processlist_id = [id['PROCESSLIST_ID'] for id in res]
    memory = [mem['current_allocated'] for mem in res]

    condition = " || ".join(f"$4=={pid}" for pid in Thread_os_id)

    try:
        res = ssm.send_command(
            InstanceIds=['i-075d1c158084640e8'],
            DocumentName='AWS-RunShellScript',
            Parameters={
                'commands': [f""" 
                    pidstat -t -p $(pidof mysqld) 1 1 | 
                    awk '{condition} {{print $4, $9, $10}}' | 
                    sort -k2 -nr | 
                    awk '!seen[$1]++'
                    """
                ]
            }
        )

        command_id = res['Command']['CommandId']
        time.sleep(3)
        cpu_utilization = {}

        while True:

            response = ssm.get_command_invocation(CommandId=command_id, InstanceId='i-075d1c158084640e8')

            if response['Status'] == 'Success':
                cpu_utilization ={
                    int(parts[0]) : float(parts[1]) / CPU_CORE
                    for line in  response['StandardOutputContent'].splitlines()
                    for parts in [line.split()]
                }
                print("CPU metrics fetched from server")
                break

            else:
                continue

        resource_utilization = {
            k:{
                'CPU_Utilization' : cpu_utilization[v], 
                'query_thread_memory_allocated':m
            } 
            for k, v, m 
            in zip(processlist_id, Thread_os_id, memory)
        }

        return resource_utilization

    except Exception as e:
        return f"error: {e}"
    

@mcp.tool()
async def get_query_execution_plan(query_text : str):
    '''
       Use when query inefficiency, poor optimization, table scans, or execution-plan-related issues are suspected. 
       Use to validate performance hypotheses.
    '''

    final_query = f"EXPLAIN FORMAT=JSON {query_text}"
    res = await db.run_admin_query(final_query)
    print(res[0]['EXPLAIN'])
    return res[0]['EXPLAIN']


@mcp.tool()
async def send_email_to_admin(subject: str, body: str): 
    
    '''
        Mandatory final step after root cause identification.
        Use this tool to send email to admin.
        Input parameters: subject, body
    '''  
    msg = MIMEText(body)
    msg["Subject"] = subject
    msg["From"] = os.getenv("USERNAME")
    msg["To"] = os.getenv("ADMIN_EMAIL")

    with smtplib.SMTP("smtp.gmail.com", 587) as server:
        server.starttls()
        server.login(
            os.getenv("USERNAME"),
            os.getenv("PASSWORD")
        )
        server.send_message(msg)

    return "Email sent successfully"


@mcp.tool()
async def get_processlist():
    '''
        Use this tool to get the list of currently running queries.
        This tool returns the result of the query similar to the output of the MySQL command "SHOW FULL PROCESSLIST" or information_schema.PROCESSLIST table.
        It provides information about the currently executing queries, including their IDs, users, hosts, databases, execution time, state, and the first 1000 characters of the query text.
    '''
    
    query = """
        SELECT
            ID, 
            USER,
            HOST,
            DB,
            TIME,
            STATE,
            LEFT(INFO,1000)
                AS QUERY_TEXT
        FROM information_schema.PROCESSLIST
        WHERE COMMAND='Query'
        AND INFO IS NOT NULL
        AND USER <> 'event_scheduler'
        AND ID <> CONNECTION_ID()
        ORDER BY TIME DESC
    """

    res = await db.run_admin_query(query)
    return res