import logging
import logging.config
import os
from pathlib import Path
from typing import Final

from dotenv import load_dotenv


# This file is expected at: app/utils/logging_config.py
SERVICE_ROOT: Final[Path] = Path(__file__).resolve().parents[1]
PROJECT_ROOT: Final[Path] = SERVICE_ROOT.parent
ENV_FILE: Final[Path] = SERVICE_ROOT / ".env"

# Load only the App service environment file.
load_dotenv(dotenv_path=ENV_FILE, override=False)

DEFAULT_SERVICE_NAME: Final[str] = "database-assistant-app"
DEFAULT_LOG_FILE_PREFIX: Final[str] = "app"
DEFAULT_LOG_LEVEL: Final[str] = "INFO"
DEFAULT_LOG_DIRECTORY: Final[Path] = PROJECT_ROOT / "logs" / "app"
DEFAULT_MAX_BYTES: Final[int] = 10 * 1024 * 1024
DEFAULT_BACKUP_COUNT: Final[int] = 10

VALID_LOG_LEVELS: Final[set[str]] = {
    "DEBUG",
    "INFO",
    "WARNING",
    "ERROR",
    "CRITICAL",
}


def get_log_level(environment_variable: str, default: str) -> str:
    """Return a validated log level from the App service environment."""

    configured_level = os.getenv(
        environment_variable,
        default,
    ).strip().upper()

    if configured_level not in VALID_LOG_LEVELS:
        return default

    return configured_level


def get_positive_integer(environment_variable: str, default: int) -> int:
    """Return a positive integer from the environment or the default."""

    configured_value = os.getenv(environment_variable)

    if configured_value is None:
        return default

    try:
        parsed_value = int(configured_value)
    except ValueError:
        return default

    return parsed_value if parsed_value > 0 else default


def _lowest_level(*level_names: str) -> int:
    """Return the lowest numeric level needed by the configured handlers."""

    return min(logging._nameToLevel[name] for name in level_names)


def setup_logging(
    service_name: str = DEFAULT_SERVICE_NAME,
    log_file_prefix: str = DEFAULT_LOG_FILE_PREFIX,
) -> None:
    """
    Configure logging once for the App service process.

    Outputs:
    - Terminal
    - logs/app/app.log
    - logs/app/app-error.log

    Call this once from app/main.py. If event_worker.py runs as a
    separate process, that process must call this function once too.
    """

    app_environment = os.getenv("APP_ENV", "development").strip().lower()

    file_log_level = get_log_level("LOG_LEVEL", DEFAULT_LOG_LEVEL)
    console_log_level = get_log_level(
        "CONSOLE_LOG_LEVEL",
        DEFAULT_LOG_LEVEL,
    )
    uvicorn_access_level = get_log_level(
        "UVICORN_ACCESS_LOG_LEVEL",
        "INFO",
    )
    langchain_log_level = get_log_level("LANGCHAIN_LOG_LEVEL", "WARNING")
    langgraph_log_level = get_log_level("LANGGRAPH_LOG_LEVEL", "WARNING")

    log_directory = Path(
        os.getenv("LOG_DIR", str(DEFAULT_LOG_DIRECTORY))
    ).expanduser().resolve()

    max_bytes = get_positive_integer("LOG_MAX_BYTES", DEFAULT_MAX_BYTES)
    backup_count = get_positive_integer(
        "LOG_BACKUP_COUNT",
        DEFAULT_BACKUP_COUNT,
    )

    log_directory.mkdir(parents=True, exist_ok=True)

    application_log_file = log_directory / f"{log_file_prefix}.log"
    error_log_file = log_directory / f"{log_file_prefix}-error.log"

    console_format = (
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )
    file_format = (
        "%(asctime)s | %(levelname)-8s | "
        f"service={service_name} | environment={app_environment} | "
        "%(name)s | %(filename)s:%(lineno)d | %(message)s"
    )

    root_level = _lowest_level(file_log_level, console_log_level)

    logging_configuration = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "console": {
                "format": console_format,
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
            "file": {
                "format": file_format,
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "level": console_log_level,
                "formatter": "console",
                "stream": "ext://sys.stdout",
            },
            "application_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": file_log_level,
                "formatter": "file",
                "filename": str(application_log_file),
                "maxBytes": max_bytes,
                "backupCount": backup_count,
                "encoding": "utf-8",
                "delay": True,
            },
            "error_file": {
                "class": "logging.handlers.RotatingFileHandler",
                "level": "ERROR",
                "formatter": "file",
                "filename": str(error_log_file),
                "maxBytes": max_bytes,
                "backupCount": backup_count,
                "encoding": "utf-8",
                "delay": True,
            },
        },
        "root": {
            "level": root_level,
            "handlers": ["console", "application_file", "error_file"],
        },
        "loggers": {
            "uvicorn.error": {
                "level": console_log_level,
                "handlers": ["console", "application_file", "error_file"],
                "propagate": False,
            },
            "uvicorn.access": {
                "level": uvicorn_access_level,
                "handlers": ["console", "application_file", "error_file"],
                "propagate": False,
            },
            "httpx": {
                "level": "WARNING",
                "handlers": ["console", "application_file", "error_file"],
                "propagate": False,
            },
            "httpcore": {
                "level": "WARNING",
                "handlers": ["console", "application_file", "error_file"],
                "propagate": False,
            },
            "urllib3": {
                "level": "WARNING",
                "handlers": ["console", "application_file", "error_file"],
                "propagate": False,
            },
            "mysql.connector": {
                "level": "WARNING",
                "handlers": ["console", "application_file", "error_file"],
                "propagate": False,
            },
            "langchain": {
                "level": langchain_log_level,
                "handlers": ["console", "application_file", "error_file"],
                "propagate": False,
            },
            "langgraph": {
                "level": langgraph_log_level,
                "handlers": ["console", "application_file", "error_file"],
                "propagate": False,
            },
        },
    }

    logging.config.dictConfig(logging_configuration)
    logging.captureWarnings(True)

    startup_logger = logging.getLogger(__name__)
    startup_logger.info(
        "Logging initialized: service=%s environment=%s "
        "file_level=%s console_level=%s log_directory=%s env_file=%s",
        service_name,
        app_environment,
        file_log_level,
        console_log_level,
        log_directory,
        ENV_FILE,
    )
