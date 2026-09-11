from datetime import datetime, timezone
from auth.database import get_auth_connection


def utc_now_without_timezone() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def find_user_by_username(username: str) -> dict | None:
    query = """
        SELECT
            id,
            username,
            email,
            display_name,
            password_hash,
            is_active
        FROM app_users
        WHERE username = %s
        LIMIT 1
    """

    with get_auth_connection() as connection:
        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(query,(username,))
            return cursor.fetchone()

        finally:
            cursor.close()


def create_session(
    *,
    user_id: int,
    token_hash: str,
    expires_at: datetime,
    ip_address: str | None,
    user_agent: str | None,
) -> None:
    
    query = """
        INSERT INTO auth_sessions (
            user_id,
            token_hash,
            expires_at,
            ip_address,
            user_agent
        )
        VALUES (%s, %s, %s, %s, %s)
    """

    with get_auth_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(query, (user_id, token_hash, expires_at, ip_address, user_agent))
            connection.commit()

        except Exception:
            connection.rollback()
            raise

        finally:
            cursor.close()


def find_user_by_session_hash(token_hash: str) -> dict | None:
    query = """
        SELECT
            u.id,
            u.username,
            u.email,
            u.display_name,
            u.is_active,
            s.id AS session_id,
            s.expires_at
        FROM auth_sessions AS s
        INNER JOIN app_users AS u
            ON u.id = s.user_id
        WHERE
            s.token_hash = %s
            AND s.revoked_at IS NULL
            AND s.expires_at > %s
            AND u.is_active = TRUE
        LIMIT 1
    """

    with get_auth_connection() as connection:
        cursor = connection.cursor(dictionary=True)

        try:
            cursor.execute(query, (token_hash, utc_now_without_timezone()))
            return cursor.fetchone()

        finally:
            cursor.close()


def update_session_last_seen(session_id: int) -> None:
    query = """
        UPDATE auth_sessions
        SET last_seen_at = %s
        WHERE id = %s
    """

    with get_auth_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(query, (utc_now_without_timezone(), session_id))
            connection.commit()

        except Exception:
            connection.rollback()
            raise

        finally:
            cursor.close()


def revoke_session(token_hash: str) -> None:
    query = """
        UPDATE auth_sessions
        SET revoked_at = %s
        WHERE
            token_hash = %s
            AND revoked_at IS NULL
    """

    with get_auth_connection() as connection:
        cursor = connection.cursor()

        try:
            cursor.execute(query, (utc_now_without_timezone(), token_hash))
            connection.commit()

        except Exception:
            connection.rollback()
            raise

        finally:
            cursor.close()