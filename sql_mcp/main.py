from fastapi import FastAPI
from contextlib import asynccontextmanager
from servers.read_db import mcp_read, router as read_router
from servers.write_db import mcp_write, router as write_router
from servers.update_db import mcp_update, router as update_router 
from servers.admin_tools import mcp_admin


@asynccontextmanager
async def lifespan(app : FastAPI):
    async with mcp_read.lifespan(app):
        async with mcp_write.lifespan(app):
            async with mcp_update.lifespan(app):
                async with mcp_admin.lifespan(app):
                    yield
    

app = FastAPI(title="MCP", lifespan=lifespan)

# REST Endpoints
app.include_router(read_router)
app.include_router(write_router)

# MCP Tool servers
app.mount("/mcp/read", mcp_read)
app.mount("/mcp/write", mcp_write)
app.mount("/mcp/update", mcp_update)
app.mount("/mcp/admin", mcp_admin)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)


