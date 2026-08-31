from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from servers.read_db import mcp_read
from servers.write_db import mcp_write
from servers.update_db import mcp_update
from servers.admin_tools import mcp_admin
from utils.downloads import CSV_DIRECTORY



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


@app.get("/downloads/{file_name}")
async def download_csv_file(
    file_name: str,
):
    safe_file_name = Path(file_name).name

    if safe_file_name != file_name:
        raise HTTPException(
            status_code=400,
            detail="Invalid file name.",
        )

    if not safe_file_name.lower().endswith(".csv"):
        raise HTTPException(
            status_code=400,
            detail="Only CSV files can be downloaded.",
        )

    file_path = (
        CSV_DIRECTORY / safe_file_name
    ).resolve()

    if file_path.parent != CSV_DIRECTORY:
        raise HTTPException(
            status_code=400,
            detail="Invalid file location.",
        )

    if (
        not file_path.exists()
        or not file_path.is_file()
    ):
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