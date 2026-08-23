from fastapi import Query, HTTPException, APIRouter
from fastmcp import FastMCP
from utils.schema import Entities
from database.db import db
from pathlib import Path
import csv
import uuid


# creates MCP server
mcp = FastMCP("Read_Database")
mcp_read = mcp.http_app(path="/")
router = APIRouter()


# Fetching tables schema from schema.py
Table_Scehma = Entities()

# folder for stroring the csv files
dir_path = Path("/home/ubuntu/DB_Project/mcp/csv_data/")
dir_path.mkdir(exist_ok=True)


@mcp.tool()
async def get_tables():
    """ 
        Returns the all available table in database
    """

    try:
        tables = Table_Scehma.show_tables()
        return tables
    except Exception as e:
        return f"Error:{str(e)}"


@router.get("/table_schema")
@mcp.tool()
async def get_columns(name: list[str] = Query(...)):
    """ 
        Returns the list of column names from tables
        Args: 
            name: Name of table required in str format
    """

    print(f"calling get column tool for {name}")
    try:
        columns = Table_Scehma.get_columns(*name)
        print(columns)
        return columns
    except Exception as e:
        return f"Error:{str(e)}"



BLOCKED_KEYWORDS = [
    "information_schema",
    "mysql.",
    "performance_schema",
    "sys.",
    "load_file",
    "sleep",
    "benchmark",
    "into outfile",
    "into dumpfile"
]


def validate_query(query): 
    """
        Returns:
            (True, message, updated_query)  -> Query should be blocked
            (False, message, updated_query) -> Query is allowed
    """

    if not query or not query.strip():
        return False, "Query cannot be empty.", None

    normalized = " ".join(query.strip().lower().split())

    # Must start with SELECT
    if not normalized.startswith("select "):
        return False, "Only Select(read only) querys' allowed", None

    # Block dangerous schemas/functions
    if any(keyword in normalized for keyword in BLOCKED_KEYWORDS):
        return False, "Query contains restricted keywords.", None

    # Query valid and unchanged
    return True, "Query is valid.", None
  


@mcp.tool()
async def direct_execute_query(query:str):
    """
        Takes sql(MySQL) query as input in string fromat.
        By using table and columns Build sql query according users intent pass as a string.
    """

    print("*"*20," direct executing query","*"*20)

    is_valid , message, modified_query = validate_query(query)   
    
    if not is_valid:
        return message
    else:
        try:    
            final_query = modified_query if modified_query else query
            
            res = await db.run_db_query(final_query)

            if len(res["query_result"]) >= 10:
                
                file_name = f"query_result_{uuid.uuid4().hex}.csv"
                file_path = dir_path / file_name

                with open(file_path, "w", encoding="utf-8", newline="") as csvfile:
                    writer = csv.DictWriter(csvfile, fieldnames=res["query_result"][0].keys()) # columns
                    writer.writeheader() # first row
                    writer.writerows(res["query_result"]) # remaining rows

                return {
                    "message" : f"fetched {len(res["query_result"])} rows. Result of query is availabe in provided csv file",
                    "file_path" : file_path 
                }

            else:
                return res
   
        except Exception as e:
                error_message = f"DB_ERROR: {str(e)}"
                print("Returning error to endpoint:", error_message)
                raise HTTPException(
                    status_code=500,
                    detail=error_message
                )

     


























































































'''

class SelectModel(BaseModel):
    Table : str
    columns : List[str]
    where : str | None = None
    limit : int | None = None

class SelectColumn(BaseModel):
    name : str
    aggregation : str | None = None  # e.g. "SUM", "COUNT"

class AggregateModel(BaseModel):
    Table : str
    select : List[SelectColumn]
    Where : str | None = None
    Group: List[str] | None = None
    having : str | None = None
    Order : List[str] | None = None 
    limit : int | None = None  

#mcp.tool() 
async def read_table(data: SelectModel):
    """
    fetch the records from database by provided input details
    Args:
        Table: Name of the table in string format.
        columns : Required columns as a list of strings.
        where : where condition in string format
        limit : Number or records want to fetch in int format.
    """
    where_cond = f" where {data.where}" if data.where is not None else ""
    Limit = f" Limit {data.limit}" if data.limit is not None else ""
    query = f" select {', '.join(data.columns)} from {data.Table}{where_cond}{Limit};"
    logging.info("query executing:",query)
    try:
        cursor.execute(query)
        res = cursor.fetchall()
        print("query_result:",res)
        return res[-1:-5:-1]
    except Exception as e:
        return f"Error:{str(e)}"


#@mcp.tool()
async def Aggregate_func(data:AggregateModel):
    """
    Use this tool to construct SQL aggregate queries on a single table. Output must follow strict SQL aggregation rules.
    Fields

    Table: table name
    select : columns names for fetching records from table
    Where: filter before aggregation
    Group: columns for GROUP BY
    having: filter after aggregation
    Order: sorting columns/expressions
    limit: max rows

    Critical Rules (STRICT – MUST FOLLOW)
        Column Consistency Rule
            Columns should contain only those columns needed by the user query
            Do NOT include unnecessary or unrelated columns

        GROUP BY Rule (Most Important)
            Group must exactly cover all non-aggregated selected columns
            No missing columns in Group
            No extra unrelated columns in Columns
            No column should exist in Columns without being in Group

        Mandatory Grouping
            If both Columns and Aggregate_col are present → Group is required
            Cannot skip or partially fill Group

         Common Mistakes to Avoid
            ❌ Adding extra columns based on table schema instead of user intent
            ❌ Missing columns in Group when multiple columns are selected
            ❌ Mixing non-aggregated columns without grouping
            ❌ Avoid passing aggregate function directly on column (COUNT(emp_no)) instead of this pass like below
                name: emp_no
                aggregation: COUNT
        🎯 Key Principle
            Only include relevant user-requested columns, and ensure
            Columns == Group (for all non-aggregated fields)
    """
    print(f"################## CALLING AGGREGATE FUNCTION FOR {data.Table}####################### ")
    column = [f"{i.aggregation}({i.name})" if i.aggregation is not None else i.name for i in data.select] 
    where_cond = f" WHERE {data.Where}" if data.Where is not None else ""
    group = f" GROUP BY {", ".join(data.Group)}" if data.Group is not None else ""
    having_cond = f" HAVING {data.having}" if data.having is not None else ""
    order = f" ORDER BY {", ".join(data.Order)}" if data.Order is not None else ""
    limit = f" LIMIT {data.limit}" if data.limit is not None else ""

    query = f"SELECT {", ".join(column)} FROM {data.Table}{where_cond}{group}{having_cond}{order}{limit};"
    print("===========QUERY EXECUTING =============================================")
    print(query)
    try:
        cursor.execute(query)
        res = cursor.fetchall()
        return res[-1:-5:-1]
    except Exception as e:
        return f"Error:{str(e)}"

''' 