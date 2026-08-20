from fastmcp import FastMCP
from utils.models import EmployeesModel, Salaries, Departments, DeptEmployee, Titles
from fastapi import APIRouter
from database.db import db

router = APIRouter()

#mcp server
mcp = FastMCP("Write_Database")
mcp_write = mcp.http_app(path="/") 


@mcp.tool()
async def employees(data : EmployeesModel):
    """ 
        Use this tool to add new employee.
        This is the main employee master table. It stores personal and joining information of each employee.
    """

    sql = "INSERT INTO employees (emp_no, birth_date, first_name, last_name, gender, hire_date) VALUES (%s, %s, %s, %s, %s, %s)"
    value = (data.emp_no, data.birth_date, data.first_name, data.last_name, data.gender, data.hire_date)
    return await db.run_db_query(sql, value)


@mcp.tool()
async def salaries(data : Salaries):
    """ 
        Use this tool for adding employees salary details.
        This table stores employee salary history.
        Requiers Unique emp_no that should be already exist in emloyees table is must.
    """

    sql = "INSERT INTO salaries (emp_no, salary, from_date, to_date) VALUES (%s, %s, %s, %s)"
    value = (data.emp_no, data.salary, data.from_date, data.to_date)
    return await db.run_db_query(sql, value)


@mcp.tool()
async def departments(data : Departments):
    """ 
        This tool stores department details.
    """

    sql = "INSERT INTO departments (dept_no, dept_name) VALUES (%s, %s)"
    value = (data.dept_no, data.dept_name)
    return await db.run_db_query(sql, value)
    

@mcp.tool()
async def deparment_employees(data : DeptEmployee):
    """ 
        This tool stores connections of employees with departments. 
        It is a relationship/history table because one employee can work in different departments over time, and one department can have many employees.
    """

    sql = "INSERT INTO dept_name (emp_no, dept_no, from_date, to_date) VALUES (%s, %s, %s, %s)"
    value = (data.emp_no, data.dept_no, data.from_date, data.to_date)
    return await db.run_db_query(sql, value)


@mcp.tool()
async def titles(data : Titles):
    """ 
        This tool stores employees job title history.
        Like from when to upto employee is working on under which title(Engineer, Manager, Senior engineer)
    """

    sql = "INSERT INTO titles (emp_no, title, from_date, to_date) VALUES (%s, %s, %s, %s)"
    value = (data.emp_no, data.title, data.from_date, data.to_date)
    return await db.run_db_query(sql, value)


@mcp.tool()
async def manager_of_departments(data : DeptEmployee):
    """ 
        This tool stores which employee managed which department and during what period.
    """
    
    sql = "INSERT INTO dept_manager (emp_no, dept_no, from_date, to_date) VALUES (%s, %s, %s, %s)"
    value = (data.emp_no, data.dept_no, data.from_date, data.to_date)
    return await db.run_db_query(sql, value)

