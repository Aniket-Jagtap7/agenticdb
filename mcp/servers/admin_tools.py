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
    print("check_resource_usage_by_queries tool executing")
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
    print("get_query_execution_plan tool executing")
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
    
    print("get_processlist tool executing")

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


@mcp.tool()
async def check_deadlocks():
    '''
        Use this tool for checking dead locks in database server.
    '''

    print("check_deadlocks tool executing")
    query = "SHOW ENGINE INNODB STATUS"
    try:
        res = await db.run_admin_query(query)
        return res
    
    except Exception as e:
        return f"Error:{e}"


@mcp.tool()
async def locking_transactions_details():
    '''
        Use to diagnose MySQL lock contention, blocked transactions, lock wait timeouts, and stuck DDL/DML operations. 
        Helps identify the blocking session, affected objects, and lock type.
    '''
    print("locking_transactions_details tool executing")
    result = {}

    try:
        # Active blockers
        active_row_lock_waits = await db.run_admin_query(query="SELECT * FROM sys.innodb_lock_waits;")
        result['active_row_lock_waits'] = active_row_lock_waits

        # Active Transactions
        active_transactions = await db.run_admin_query(query="SELECT trx_id, trx_started, trx_state, trx_mysql_thread_id, trx_query FROM information_schema.innodb_trx;")
        result['active_transactions'] = active_transactions

        # Metadata Locks
        query = """
            SELECT
                t.processlist_id,
                ml.object_schema,
                ml.object_name,
                ml.lock_type,
                ml.lock_status
            FROM performance_schema.metadata_locks ml
            JOIN performance_schema.threads t
            ON ml.owner_thread_id = t.thread_id;
        """
        meatadata_locks = await db.run_admin_query(query=query)
        result['meatadata_locks'] = meatadata_locks

        # row level lock details
        query="""
            SELECT
                dw.REQUESTING_ENGINE_TRANSACTION_ID,
                dw.BLOCKING_ENGINE_TRANSACTION_ID,
                dl1.OBJECT_NAME AS waiting_table,
                dl2.OBJECT_NAME AS blocking_table
            FROM performance_schema.data_lock_waits dw
            JOIN performance_schema.data_locks dl1
                ON dw.REQUESTING_ENGINE_LOCK_ID = dl1.ENGINE_LOCK_ID
            JOIN performance_schema.data_locks dl2
                ON dw.BLOCKING_ENGINE_LOCK_ID = dl2.ENGINE_LOCK_ID;
        """
        row_level_locks = await db.run_admin_query(query=query)
        result['row_level_locks'] = row_level_locks

        return result
    
    except Exception as e:
        return f"Error:{e}"
    

@mcp.tool()
async def buffer_pool_health_check():
    '''
        Checks MySQL InnoDB Buffer Pool health. Use for slow performance or high disk I/O investigations when locking is not the primary issue. 
        Returns cache hit ratio, physical reads, buffer pool size, free pages, and dirty pages to identify memory pressure and caching inefficiencies.
    '''

    print("buffer_pool_health_check tool executing")
    buffer_values = {}
    result = {}

    try:
        pool_size = await db.run_admin_query(query="SHOW VARIABLES LIKE 'innodb_buffer_pool_size';")
        buffer_values[pool_size[0]['Variable_name']] = pool_size[0]['Value']

        read_req = await db.run_admin_query(query="SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_read%';")
        for row in read_req:
            buffer_values[row["Variable_name"]] = int(row["Value"])

        pool_pages = await db.run_admin_query(query="SHOW GLOBAL STATUS LIKE 'Innodb_buffer_pool_pages%';")
        for row in pool_pages:
            buffer_values[row["Variable_name"]] = int(row['Value'])

        result["buffer_pool_size_bytes"] = buffer_values.get("innodb_buffer_pool_size", None)
        result["read_requests"] =  buffer_values.get("Innodb_buffer_pool_read_requests", 0)
        result["physical_reads"] = buffer_values.get("Innodb_buffer_pool_reads", 0)
        result["hit_ratio_percent"] = round((1- (result["physical_reads"] / result["read_requests"])) * 100, 2)
        result["pages_total"] = buffer_values.get("Innodb_buffer_pool_pages_total", 0)
        result["pages_free"] = buffer_values.get("Innodb_buffer_pool_pages_free", 0)
        result["pages_data"] = buffer_values.get("Innodb_buffer_pool_pages_data", 0)
        result["pages_dirty"] = buffer_values.get("Innodb_buffer_pool_pages_dirty", 0)
        result["free_percent"] = round(result["pages_free"]*100/result["pages_total"], 2) if result["pages_total"] else 0
        result["dirty_percent"] = round(result["pages_dirty"]*100/result["pages_total"], 2) if result["pages_total"] else 0
        
        return result
        
    except Exception as e:
        return f"Error:{e}"


@mcp.tool()
async def mysql_innodb_diagnostics():
    '''
        Collects detailed InnoDB diagnostic information. Use during deep performance investigations involving locks, 
        deadlocks, long-running transactions, buffer pool issues, flushing pressure, or storage bottlenecks. 
        Returns InnoDB internal status useful for root cause analysis when standard health metrics are insufficient.
    '''

    print("mysql_innodb_diagnostics tool executing..")
    try:
        res = await db.run_admin_query(query="SHOW ENGINE INNODB STATUS")
        return res[0]
    except Exception as e:
        return f"Error:{e}"


@mcp.tool()
async def top_sql_analysis():
    '''
        Shows the top query patterns consuming database resources. Use when investigating slow performance, high CPU,
        or query-related load. Returns execution count, total and average latency, rows examined, rows returned, errors,
        and warnings for the most expensive SQL patterns.
    '''
    print("top_sql_analysis tool executing")

    try:
        query="""
        SELECT
            DIGEST_TEXT,
            COUNT_STAR,
            ROUND(SUM_TIMER_WAIT / 1000000000000, 2) TOTAL_SEC,
            ROUND(AVG_TIMER_WAIT / 1000000000000,2) AVG_SEC,
            SUM_ROWS_EXAMINED,
            SUM_ROWS_SENT,
            SUM_ERRORS,
            SUM_WARNINGS
        FROM performance_schema
            .events_statements_summary_by_digest

        WHERE DIGEST_TEXT IS NOT NULL

        AND DIGEST_TEXT NOT LIKE
            '%PROCESSLIST%'

        AND DIGEST_TEXT NOT LIKE
            '%information_schema%'

        AND DIGEST_TEXT NOT LIKE
            '%performance_schema%'

        AND DIGEST_TEXT NOT LIKE
            '%SHOW GLOBAL STATUS%'

        AND DIGEST_TEXT NOT LIKE
            '%SHOW VARIABLES%'

        AND DIGEST_TEXT NOT LIKE
            '%SHOW REPLICA STATUS%'

        AND DIGEST_TEXT NOT LIKE
            '%innodb_lock_waits%'

        AND DIGEST_TEXT NOT LIKE
            '%SET autocommit%'

        AND DIGEST_TEXT NOT LIKE
            '%SET NAMES%'

        AND DIGEST_TEXT NOT LIKE
            '%version_comment%'

        ORDER BY SUM_TIMER_WAIT DESC
        LIMIT 10       
        """

        res = await db.run_admin_query(query=query)
        return res[0]

    except Exception as e:
        return f"Error:{e}"


@mcp.tool()
async def wait_event_analysis():
    '''
        Identifies the resources MySQL spends time waiting on. Use when slow performance cannot be explained by locks, 
        CPU, execution plans, or buffer pool metrics. Returns top wait events including disk I/O, metadata locks, 
        InnoDB synchronization, and internal resource contention to help identify hidden bottlenecks.
    '''
    print("wait_event_analysis tool executing..")
    query="""
        SELECT
            EVENT_NAME,
            COUNT_STAR,
            ROUND(SUM_TIMER_WAIT / 1000000000000, 2) AS TOTAL_SEC,
            ROUND(AVG_TIMER_WAIT / 1000000000000, 6) AS AVG_SEC
        FROM performance_schema.events_waits_summary_global_by_event_name
        WHERE
            SUM_TIMER_WAIT > 0
            AND (
                EVENT_NAME LIKE 'wait/io/%'
                OR EVENT_NAME LIKE 'wait/lock/%'
                OR EVENT_NAME LIKE 'wait/synch/%'
            )
        ORDER BY SUM_TIMER_WAIT DESC
        LIMIT 20;
    """

    try:
        res = await db.run_admin_query(query)
        return res
    except Exception as e:
        return f"Error:{e}"