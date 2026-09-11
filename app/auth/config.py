import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def get_boolean_environment(name: str, default: bool,) -> bool:
    value = os.getenv(name, str(default),)

    return value.strip().lower() in {"true", "1", "yes", "on"}


@dataclass(frozen=True)
class AuthSettings:
    db_host: str
    db_port: int
    db_name: str
    db_user: str
    db_password: str
    db_pool_size: int

    session_cookie_name: str
    session_hours: int
    cookie_secure: bool
    cookie_samesite: str


settings = AuthSettings(
    db_host=os.getenv("AUTH_DB_HOST", "127.0.0.1"),
    db_port=int(os.getenv("AUTH_DB_PORT", "3306")),
    db_name=os.getenv("AUTH_DB_NAME", ""),
    db_user=os.getenv("AUTH_DB_USER", ""),
    db_password=os.getenv("AUTH_DB_PASSWORD", ""),
    db_pool_size=int(os.getenv("AUTH_DB_POOL_SIZE", "5")),
    session_cookie_name=os.getenv("AUTH_SESSION_COOKIE_NAME", "db_copilot_session"),
    session_hours=int(os.getenv("AUTH_SESSION_HOURS", "8")),
    cookie_secure=get_boolean_environment("AUTH_COOKIE_SECURE", False),
    cookie_samesite=os.getenv("AUTH_COOKIE_SAMESITE", "lax")
)