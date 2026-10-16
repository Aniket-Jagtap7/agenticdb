from contextlib import contextmanager
from mysql.connector.pooling import  MySQLConnectionPool
from auth.config import settings


auth_connection_pool = MySQLConnectionPool(
    pool_name="database_copilot_auth",
    pool_size=settings.db_pool_size,
    pool_reset_session=True,
    host=settings.db_host,
    port=settings.db_port,
    database=settings.db_name,
    user=settings.db_user,
    password=settings.db_password,
    autocommit=False,
)


@contextmanager
def get_auth_connection():
    connection = (auth_connection_pool.get_connection())

    try:
        yield connection
    finally:
        connection.close()