from database.db import db
import asyncio
from servers.admin_tools import get_processlist



res = asyncio.run(get_processlist())
print(res)





