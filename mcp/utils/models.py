from pydantic import BaseModel, Field, field_validator,  BeforeValidator
from enum import Enum
from datetime import date, datetime
from typing import Annotated


def parse_dd_mm_yyyy(value):
    if isinstance(value, date):
        return value.strftime("%d-%m-%Y")

    formats = [
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%d.%m.%Y",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y.%m.%d",
    ]

    for fmt in formats:
        try:
            parsed = datetime.strptime(value, fmt).date()
            return parsed
        except (ValueError, TypeError):
            continue

    raise ValueError("Invalid date format")

Date = Annotated[date, BeforeValidator(parse_dd_mm_yyyy)]

#--------------------Models for Data Insert validation-----------------------------------------------------------
class Gender(str, Enum):
    male = "M"
    female = "F"

class EmployeesModel(BaseModel):
    emp_no : int = Field(description="Unique Employee No.")
    birth_date : Date = Field(description=" Birth date of employee")
    first_name : str = Field(min_length=2, max_length=14, description="First Name of Employee")
    last_name : str = Field(min_length=2, max_length=16, description="Last Name of Employee")
    gender : Gender = Field(description="Gender of Employee")
    hire_date : Date = Field(description="Date When employee was hired")


class Salaries(BaseModel):
    emp_no : int = Field(description="Unique Employee No.")
    salary : int = Field(description="Salary of the employee")
    from_date : Date = Field(description="Date from which employee started working in that department.")
    to_date : Date = Field(description="Date until which employee worked in that department. A future date like 9999-01-01 usually means current record.")

        
class Departments(BaseModel):
    dept_no : str = Field(max_length=4, description= "Department ID")
    dept_name : str = Field(max_length=40, description="Department name, for example Marketing, Sales, Development. Uniqe Key")


class Titles(BaseModel):
    emp_no : int = Field(description="Unique Employee No.")
    title : str = Field(max_length=50, description="Employee’s job title, for example Engineer, Senior Engineer, Manager.")
    from_date : Date = Field(description="Date from which employee started working in that department.")
    to_date : Date = Field(description="Date until which employee worked in that department. A future date like 9999-01-01 usually means current record.")

# Can be used for both dept_manager and dept_employee tables
class DeptEmployee(BaseModel):
    emp_no : int = Field(description="Unique Employee No.")
    dept_no : str = Field(max_length=4, description= "Department ID")
    from_date : Date = Field(description="Date from which employee started working in that department.")
    to_date : Date = Field(description="Date until which employee worked in that department. A future date like 9999-01-01 usually means current record.")


# Resource check model
class ResourceCheck(BaseModel):
    query_id : tuple[int] 