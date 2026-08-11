import asyncio
from mysql.connector.pooling import MySQLConnectionPool
from dotenv import load_dotenv
import os

load_dotenv()

class Database:

    _instance = None
    _pool = None

    def __new__(cls):

        if cls._instance is None:
            cls._instance = super().__new__(cls)

            try:
                cls._pool = MySQLConnectionPool(
                    pool_name="mcp_pool",
                    pool_size=20,
                    pool_reset_session=True,
                    host="localhost",
                    user=os.getenv("user"),
                    password=os.getenv("password"),
                    database=os.getenv("database"),
                    port=3306,
                    connection_timeout=10
                )

                cls._admin_pool = MySQLConnectionPool(               
                    pool_name="admin_pool",
                    pool_size=5,                
                    host=os.getenv("host"),                
                    user=os.getenv("DB_ADMIN_USER"),              
                    password=os.getenv("DB_ADMIN_PASSWORD"),                
                    database=os.getenv("database"),
                    connection_timeout=10        
                )

            except Exception as e:  
                cls._admin_pool = None
                cls._pool = None
                cls._pool_error = f"DB_Error: {e}"
            
        return cls._instance


    def execute_query(self, query: str, value=None):

        if self._pool is None:
            return self._pool_error

        conn = None

        try:
            conn = self._pool.get_connection()

            with conn.cursor(buffered=True) as cursor:
                if value is not None:
                    cursor.execute(query, value)
                else:
                    cursor.execute(query)

                query_type = query.strip().split()[0].lower()

                if query_type in (
                    "select",
                    "show",
                    "describe",
                    "desc",
                    "explain"
                ):

                    result = cursor.fetchall()
                    warnings = []

                    try:
                        warnings = cursor.fetchwarnings() or []
                    except Exception:
                        pass

                    return {
                        "query_result": result[-1:-7:-1],
                        "warnings": warnings[:10]
                    }

                conn.commit()

                return {
                    "message": "Success"
                }

        except Exception as e:

            if conn:
                conn.rollback()

            return f"DB_ERROR: {str(e)}"

        finally:

            if conn and conn.is_connected():
                conn.close()


    def execute_admin_query(self, query: str, value=None):

        if self._admin_pool is None:
            return self._pool_error

        conn = None

        try:
            conn = self._admin_pool.get_connection()

            with conn.cursor(buffered=True, dictionary=True) as cursor:
                if value is not None:
                    cursor.execute(query, value)
                else:
                    cursor.execute(query)

                query_type = query.strip().split()[0].lower()

                if query_type in (
                    "select",
                    "show",
                    "describe",
                    "desc",
                    "explain"
                ):
                    result = cursor.fetchall()

                    return result

                conn.commit()

                return {
                    "message": "Success"
                }

        except Exception as e:
            if conn:
                conn.rollback()

            return f"DB_ERROR: {str(e)}"

        finally:
            if conn and conn.is_connected():
                conn.close()


    async def run_db_query(self, query: str, value=None):

        return await asyncio.to_thread(
            self.execute_query,
            query,
            value
        )


    async def run_admin_query(self, query: str, value=None):
        return await asyncio.to_thread(
            self.execute_admin_query,
            query,
            value
        )


db = Database()