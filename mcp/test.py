from database.db import db
import asyncio
from servers.update_db import count_rows


query = "UPDATE titles SET title = 'Senior Engineer' WHERE emp_no = 500026;"

res = asyncio.run(count_rows(query=query))

print(res)






