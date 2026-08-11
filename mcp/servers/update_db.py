from fastmcp import FastMCP
from fastapi import APIRouter
from sqlglot import parse_one, exp
from database.db import db

router = APIRouter()

#mcp server
mcp = FastMCP("Update_Database")
mcp_update = mcp.http_app(path="/") 


def update_to_count_query(update_sql):

    ast = parse_one(update_sql, dialect="mysql")
    update_table = ast.this.sql(dialect="mysql")
    joins = ast.args.get("joins", [])
    where_clause = ast.args.get("where")

    conditions = []
    if where_clause:
        conditions.append(
            where_clause.this.sql(dialect="mysql")
        )

    set_conditions = []

    for assignment in ast.args.get("expressions", []):

        left = assignment.this
        right = assignment.expression

        # Only handle literal assignments
        if isinstance(right, exp.Literal):

            column = left.sql(dialect="mysql")
            value = right.sql(dialect="mysql")
            set_conditions.append(
                f"{column} <> {value}"
            )

            set_conditions.append(
                f"{column} IS NULL"
            )

    if set_conditions:
        conditions.append(
            "(" + " OR ".join(set_conditions) + ")"
        )

    sql_parts = [
        "SELECT COUNT(*) AS affected_rows",
        f"FROM {update_table}"
    ]

    for join in joins:
        sql_parts.append(
            join.sql(dialect="mysql")
        )

    if conditions:
        sql_parts.append(
            "WHERE " + "\nAND ".join(conditions)
        )

    return "\n".join(sql_parts)


@mcp.tool()
async def count_rows(query : str):
    read_query = update_to_count_query(query)
    row_count = await db.run_db_query(read_query)
    #row_count = await update_data(read_query)
    return f"{row_count[0][0]} rows will be affected"

@mcp.tool() 
async def run_db_query(query : str):
    '''
        Use this tool for executing sql query. 
    '''
    #res = await update_data(query)
    res = await db.run_db_query(query) 
    return res



