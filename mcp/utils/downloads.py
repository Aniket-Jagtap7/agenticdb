import os

from pathlib import Path
from urllib.parse import quote

from dotenv import load_dotenv


load_dotenv()


CSV_DIRECTORY = Path(
    "/home/ubuntu/DB_Project/mcp/csv_data"
).resolve()


MCP_PUBLIC_BASE_URL = os.getenv(
    "MCP_PUBLIC_BASE_URL",
    "http://127.0.0.1:8000",
).rstrip("/")


def create_download_url(
    file_path_value: str | Path,
) -> dict[str, str]:
    """
    Validate a generated CSV path and return safe download
    metadata without exposing the physical filesystem path.
    """

    file_path = Path(file_path_value).resolve()

    if (
        not file_path.exists()
        or not file_path.is_file()
    ):
        raise FileNotFoundError(
            f"Generated CSV file does not exist: {file_path}"
        )

    if file_path.suffix.lower() != ".csv":
        raise ValueError(
            "Only generated CSV files can be downloaded."
        )

    if (
        file_path.parent != CSV_DIRECTORY
        and CSV_DIRECTORY not in file_path.parents
    ):
        raise ValueError(
            "The generated file is outside the CSV directory."
        )

    file_name = file_path.name

    return {
        "file_name": file_name,
        "download_url": (
            f"{MCP_PUBLIC_BASE_URL}"
            f"/downloads/{quote(file_name)}"
        ),
    }