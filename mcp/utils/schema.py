entity  = {
    "employees" :{
        "description": "This is the main employee master table. It stores personal and joining information of each employee.",
        "fields":[
            {
                "name" : "emp_no",
                "description" : "Unique employee number / employee ID. This is the primary key."
            },
            {
                "name" : "birth_date",
                "description" : "Employee’s date of birth."
            },
            {
                "name" : "first_name",
                "description" : "Employee’s first name."
            },
            {
                "name" : "last_name",
                "description" : "Employee’s last name."
            },
            {
                "name" : "gender",
                "description": "Employee gender: M = Male, F = Female."
            },
            {
                "name" : "hire_date",
                "description" : "Date when the employee joined the company."
            }
        ]
    },

    "departments":{
        "description" : "This table stores department details.",
        "fields" : [
            {
                "name" : "dept_no",
                "description": "Unique department number/code, for example d001, d002. Primary key."
            },
            {
                "name" : "dept_name",
                "description": "Department name, for example Marketing, Sales, Development. Uniqe Key"
            }
        ]
    },

    "dept_emp" :{
        "description" : "This table connects employees with departments. It is a relationship/history table because one employee can work in different departments over time, and one department can have many employees.",
        "fields" :[
            {
                "name" : "emp_no",
                "description" : "Employee ID. Foreign key referencing employees.emp_no."
            },
            {
                "name" : "dept_no",
                "description" : "Department ID. Foreign key referencing departments.dept_no."
            },
            {
                "name" : "from_date",
                "description" : "Date from which employee started working in that department."
            },
            {
                "name" : "to_date",
                "description" : "Date until which employee worked in that department. A future date like 9999-01-01 usually means current record."
            }
        ]
    },

    "dept_manager" :{
        "description" : "This table stores which employee managed which department and during what period.",
        "fields" :[
            {
                "name" : "emp_no",
                "description" : "Employee ID of the manager. Foreign key referencing employees.emp_no."
            },
            {
                "name" : "dept_no",
                "description" : "Department ID managed by the employee. Foreign key referencing departments.dept_no."
            },
            {
                "name" : "from_date",
                "description" : "Date from which the employee became manager of that department."
            },
            {
                "name" : "to_date",
                "description" : "Date until which employee was manager. Future date can mean current manager."
            }
        ]
    },

    "titles" :{
        "description" : "This table stores employee job title history.",
        "fields" :[
            {
                "name" : "emp_no",
                "description" : "Employee ID. Foreign key referencing employees.emp_no."
            },
            {
                "name" : "title",
                "description" : "Employee’s job title, for example Engineer, Senior Engineer, Manager."
            },
            {
                "name" : "from_date",
                "description" : "Date from which this title started."
            },
            {
                "name" : "to_date",
                "description" : "Date until which this title was valid. Future date can mean current title."
            }
        ]
    },

    "salaries" :{
        "description" : "This table stores employee salary history.",
        "fields" :[
            {
                "name" : "emp_no",
                "description" : "Employee ID. Foreign key referencing employees.emp_no. Primary key"
            },
            {
                "name" : "salary",
                "description" : "Salary amount. Some versions call this column amount."
            },
            {
                "name" : "from_date",
                "description" : "Date from which this salary became effective. Primary Key"
            },
            {
                "name" : "to_date",
                "description" : "Date until which this salary was valid. Future date can mean current salary."
            }
        ]
    }
}


class Entities:
    entity = entity

    def show_tables(self):
        tables = [{'name':i, 'description':entity[i]["description"]} for i in entity.keys()]
        return tables
    
    def get_columns(self, *args):
        res = [{"table_name":arg, "columns":entity[arg]["fields"]} for arg in args]
        return res
    


