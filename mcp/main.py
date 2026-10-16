from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from servers.read_db import mcp_read
from servers.write_db import mcp_write
from servers.update_db import mcp_update
from servers.admin_tools import mcp_admin
from database.db import db
from utils.downloads import CSV_DIRECTORY
from utils.logging_config import setup_logging
import logging


setup_logging(service_name="database-assistant-mcp", log_file_prefix="mcp") 
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp_read.lifespan(app):
        async with mcp_write.lifespan(app):
            async with mcp_update.lifespan(app):
                async with mcp_admin.lifespan(app):
                    yield


app = FastAPI(title="MCP", lifespan=lifespan)


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "mcp",
    }

@app.get("/health/db")
async def health_db():
    try:
        if db.check_connection():
            return {
                "status": "ok",
                "service": "mcp",
                "database": "connected"
            }
        else:   
            raise HTTPException(
                status_code=500,
                detail="Database connection failed.",
            )
    except Exception as e:
        logger.error("Database health check failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Database health check failed: {str(e)}",
        )


@app.get("/downloads/{file_name}")
async def download_csv_file(file_name: str):
    safe_file_name = Path(file_name).name

    if safe_file_name != file_name:
        logger.warning("Invalid file name attempted: %s", file_name)
        raise HTTPException(
            status_code=400,
            detail="Invalid file name.",
        )

    if not safe_file_name.lower().endswith(".csv"):
        logger.warning("Invalid file type attempted: %s", file_name)
        raise HTTPException(
            status_code=400,
            detail="Only CSV files can be downloaded.",
        )

    file_path = (CSV_DIRECTORY / safe_file_name).resolve()

    if file_path.parent != CSV_DIRECTORY:
        logger.warning("Invalid file location attempted: %s", file_name)
        raise HTTPException(
            status_code=400,
            detail="Invalid file location.",
        )

    if (not file_path.exists() or not file_path.is_file()):
        logger.warning("File not found or not a file: %s", file_name)
        raise HTTPException(
            status_code=404,
            detail="CSV file not found.",
        )

    return FileResponse(
        path=file_path,
        filename=safe_file_name,
        media_type="text/csv",
    )


app.mount("/mcp/read", mcp_read)
app.mount("/mcp/write", mcp_write)
app.mount("/mcp/update", mcp_update)
app.mount("/mcp/admin", mcp_admin)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )