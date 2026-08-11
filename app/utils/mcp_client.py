from langchain_mcp_adapters.client import MultiServerMCPClient


READ_URL = "http://localhost:8000/mcp/read/"
WRITE_URL = "http://localhost:8000/mcp/write/"
UPDATE_URL = "http://localhost:8000/mcp/update/"
ADMIN_URL = "http://localhost:8000/mcp/admin/" 


class MCPTools:
    
    @classmethod
    async def read_tools(cls):
        return await cls._get_tools(READ_URL)

    @classmethod
    async def write_tools(cls):
        return await cls._get_tools(WRITE_URL)

    @classmethod
    async def update_tools(cls):
        return await cls._get_tools(UPDATE_URL)

    @classmethod
    async def admin_tools(cls):
        return await cls._get_tools(ADMIN_URL)

    @staticmethod
    async def _get_tools(url: str):
        client = MultiServerMCPClient(
            {
                "database": {
                    "transport": "http",
                    "url": url,
                }
            }
        )

        return await client.get_tools()


