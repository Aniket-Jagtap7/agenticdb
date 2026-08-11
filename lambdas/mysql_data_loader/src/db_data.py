import os
import mysql.connector

def get_connection():
    return mysql.connector.connect(
        host=os.getenv("host"),
        user=os.getenv("user"),
        password=os.getenv("password"),
        connection_timeout=10
    )


def get_single_status(cursor, metric_name):
    cursor.execute(
        f"SHOW GLOBAL STATUS LIKE '{metric_name}'"
    )

    result = cursor.fetchone()
    if result:
        return result["Value"]

    return None


def get_single_variable(cursor, variable_name):
    cursor.execute(
        f"SHOW VARIABLES LIKE '{variable_name}'"
    )

    result = cursor.fetchone()

    if result:
        return result["Value"]
    return None

def generate_db_report():
    db_report = {}
    conn = None
    cursor = None

    try:
        try:
            conn = get_connection()

            if not conn or  not conn.is_connected():
                return {
                    "status" : "failed",
                    "message" : "Database Connection failed"
                }
            
            cursor = conn.cursor(dictionary=True)

        except Exception as conn_error:
            return{
                "status": "FAILED",                
                "message": "Connection unsuccessful",               
                "error": str(conn_error)
            }

        # 1. WORKLOAD
        cursor.execute("""
        SELECT COUNT(*) AS active_sessions
        FROM information_schema.PROCESSLIST
        WHERE COMMAND <> 'Sleep'
        """)

        db_report["database_activity_summary"] = {
            "currently_active_sessions":
                cursor.fetchone()["active_sessions"],

            "currently_executing_threads":
                int(
                    get_single_status(
                        cursor,
                        "Threads_running"
                    ) or 0
                ),

            "currently_connected_sessions":
                int(
                    get_single_status(
                        cursor,
                        "Threads_connected"
                    ) or 0
                ),

            "total_client_requests":
                int(
                    get_single_status(
                        cursor,
                        "Questions"
                    ) or 0
                ),

            "total_queries_executed":
                int(
                    get_single_status(
                        cursor,
                        "Queries"
                    ) or 0
                )
        }

        # 2. CONNECTIONS
        max_used_connections = int(
            get_single_status(
                cursor,
                "Max_used_connections"
            ) or 0
        )

        max_connections = int(
            get_single_variable(
                cursor,
                "max_connections"
            ) or 1
        )

        connection_utilization = round(
            (max_used_connections / max_connections) * 100,
            2
        )

        db_report["connection_capacity_analysis"] = {
            "peak_connections_observed":
                max_used_connections,

            "configured_connection_limit":
                max_connections,

            "connection_utilization_percent":
                connection_utilization
        }

        # 3. LONG RUNNING QUERIES
        cursor.execute("""
        SELECT
            ID,
            USER,
            DB,
            TIME,
            STATE,
            LEFT(INFO,500) AS QUERY_TEXT
        FROM information_schema.PROCESSLIST
        WHERE COMMAND <> 'Sleep'
        AND TIME > 30
        ORDER BY TIME DESC
        """)

        db_report["currently_running_queries_over_30_seconds"] = (
            cursor.fetchall()
        )

        # 4. TOP SQL
        cursor.execute("""
        SELECT
            DIGEST_TEXT,
            COUNT_STAR,
            ROUND(
                SUM_TIMER_WAIT /
                1000000000000,
                2
            ) TOTAL_SEC,
            ROUND(
                AVG_TIMER_WAIT /
                1000000000000,
                2
            ) AVG_SEC
        FROM performance_schema
            .events_statements_summary_by_digest

        WHERE DIGEST_TEXT IS NOT NULL

        AND DIGEST_TEXT NOT LIKE
            '%PROCESSLIST%'

        AND DIGEST_TEXT NOT LIKE
            '%information_schema%'

        AND DIGEST_TEXT NOT LIKE
            '%performance_schema%'

        AND DIGEST_TEXT NOT LIKE
            '%SHOW GLOBAL STATUS%'

        AND DIGEST_TEXT NOT LIKE
            '%SHOW VARIABLES%'

        AND DIGEST_TEXT NOT LIKE
            '%SHOW REPLICA STATUS%'

        AND DIGEST_TEXT NOT LIKE
            '%innodb_lock_waits%'

        AND DIGEST_TEXT NOT LIKE
            '%SET autocommit%'

        AND DIGEST_TEXT NOT LIKE
            '%SET NAMES%'

        AND DIGEST_TEXT NOT LIKE
            '%version_comment%'

        ORDER BY SUM_TIMER_WAIT DESC
        LIMIT 10
        """)

        db_report["highest_resource_consuming_sql_patterns"] = (
            cursor.fetchall()
        )

        # 5. TRANSACTIONS
        cursor.execute("""
        SELECT
            trx_id,
            trx_state,
            trx_started,
            TIMESTAMPDIFF(
                SECOND,
                trx_started,
                NOW()
            ) age_sec
        FROM information_schema.innodb_trx
        ORDER BY age_sec DESC
        """)

        db_report["active_innodb_transactions"] = (
            cursor.fetchall()
        )

        # 6. LOCK WAITS
        cursor.execute("""
        SELECT *
        FROM sys.innodb_lock_waits
        """)

        db_report["current_lock_contention_details"] = (
            cursor.fetchall()
        )

        # 7. DEADLOCKS
        deadlocks = get_single_status(
            cursor,
            "Innodb_deadlocks"
        )

        db_report["deadlock_statistics"] = {
            "innodb_deadlocks":
                int(deadlocks)
                if deadlocks
                else 0
        }

        # 8. ROW LOCK STATS
        row_lock_stats = {}

        cursor.execute("""
        SHOW GLOBAL STATUS
        LIKE 'Innodb_row_lock%'
        """)

        for row in cursor.fetchall():
            row_lock_stats[
                row["Variable_name"]
            ] = row["Value"]

        db_report["row_lock_behavior_statistics"] = (
            row_lock_stats
        )

        # 9. TEMP TABLES
        tmp_table_stats = {}

        cursor.execute("""
        SHOW GLOBAL STATUS
        LIKE 'Created_tmp%'
        """)

        for row in cursor.fetchall():
            tmp_table_stats[
                row["Variable_name"]
            ] = row["Value"]

        db_report["temp_table_stats"] = (
            tmp_table_stats
        )

        # 10. FULL SCAN INDICATORS
        handler_stats = {}

        cursor.execute("""
        SHOW GLOBAL STATUS
        LIKE 'Handler_read%'
        """)

        for row in cursor.fetchall():

            handler_stats[
                row["Variable_name"]
            ] = row["Value"]

        db_report[
            "table_scan_and_index_usage_indicators"
        ] = handler_stats

        # 11. ABORTED CONNECTIONS
        aborted_stats = {}

        cursor.execute("""
        SHOW GLOBAL STATUS
        LIKE 'Aborted%'
        """)

        for row in cursor.fetchall():

            aborted_stats[
                row["Variable_name"]
            ] = row["Value"]

        db_report[
            "aborted_connections"
        ] = aborted_stats

        # 12. BUFFER POOL HEALTH
        buffer_values = {}

        cursor.execute("""
        SHOW GLOBAL STATUS
        LIKE
        'Innodb_buffer_pool_read%'
        """)

        for row in cursor.fetchall():

            buffer_values[
                row["Variable_name"]
            ] = int(row["Value"])

        read_requests = (
            buffer_values.get(
                "Innodb_buffer_pool_read_requests",
                0
            )
        )

        reads = (
            buffer_values.get(
                "Innodb_buffer_pool_reads",
                0
            )
        )

        hit_ratio = 0

        if read_requests > 0:
            hit_ratio = round(
                (
                    1 -
                    (
                        reads /
                        read_requests
                    )
                ) * 100,
                2
            )

        db_report["buffer_pool"] = {
            "read_requests":
                read_requests,

            "physical_reads":
                reads,

            "hit_ratio_percent":
                hit_ratio
        }

        # 13. SLOW QUERIES
        db_report["slow_query_statistics"] = {

            "slow_queries":
                int(
                    get_single_status(
                        cursor,
                        "Slow_queries"
                    ) or 0
                )
        }

        # ACTIVE QUERY SNAPSHOT 
        cursor.execute("""
        SELECT
            ID,
            USER,
            HOST,
            DB,
            TIME,
            STATE,
            LEFT(INFO,1000)
                AS QUERY_TEXT
        FROM information_schema.PROCESSLIST
        WHERE COMMAND='Query'
        AND INFO IS NOT NULL
        AND USER <> 'event_scheduler'
        AND ID <> CONNECTION_ID()
        ORDER BY TIME DESC
        """)

        db_report[
            "live_processlist_active_queries"
        ] = cursor.fetchall()

        # REPLICATION
        try:
            cursor.execute(
                "SHOW REPLICA STATUS"
            )
            replica = cursor.fetchone()

            if replica:
                db_report[
                    "replication_health_status"
                ] = {
                    "seconds_behind_source":
                        replica.get(
                            "Seconds_Behind_Source"
                        ),

                    "replica_io_running":
                        replica.get(
                            "Replica_IO_Running"
                        ),

                    "replica_sql_running":
                        replica.get(
                            "Replica_SQL_Running"
                        )
                }

        except Exception:
            pass
        return db_report

    finally:
        if cursor:
            cursor.close()

        if conn and conn.is_connected():
            conn.close()
    