# common/db/database.py

from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
from contextlib import contextmanager
import logging
from common.config import DB_CONFIG

logger = logging.getLogger(__name__)

# Create a global connection pool
pool = None


def initialize_pool(min_conn=1, max_conn=10):
    global pool
    try:
        pool = ThreadedConnectionPool(
            min_conn,
            max_conn,
            host=DB_CONFIG["host"],
            port=DB_CONFIG["port"],
            dbname=DB_CONFIG["dbname"],
            user=DB_CONFIG["user"],
            password=DB_CONFIG["password"]
        )
        logger.info("DB connection pool initialized")
    except Exception as e:
        logger.error(f"Failed to initialize connection pool: {e}")
        raise


@contextmanager
def get_db_connection():
    """
    Context manager for database connections.
    Ensures connections are always returned to the pool, even if an exception occurs.
    """
    global pool
    if pool is None:
        initialize_pool()

    conn = None
    try:
        conn = pool.getconn()
        yield conn
    finally:
        if conn is not None:
            pool.putconn(conn)


def return_connection(conn):
    """Return a connection to the pool"""
    global pool
    if pool is not None and conn is not None:
        pool.putconn(conn)


@contextmanager
def get_db_cursor(commit=True):
    """
    Context manager for database cursors.
    Handles committing or rolling back transactions and ensures proper connection release.
    """
    with get_db_connection() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        try:
            yield cursor
            if commit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()


def execute_query(sql, params=None, fetch=False, fetchone=False, commit=True):
    """
    Execute a SQL query with proper transaction handling.
    Uses context managers to ensure connections are always returned to the pool.
    """
    try:
        with get_db_cursor(commit=commit) as cur:
            cur.execute(sql, params)

            if fetchone:
                result = cur.fetchone()
            elif fetch:
                result = cur.fetchall()
            else:
                result = cur

            return result
    except Exception as e:
        logger.error(f"Database error: {e}, SQL: {sql}, Params: {params}")
        raise
