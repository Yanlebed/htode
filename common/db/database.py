# common/db/database.py - Use connection pooling

from psycopg2.pool import ThreadedConnectionPool
from psycopg2.extras import RealDictCursor
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

def get_connection():
    global pool
    if pool is None:
        initialize_pool()
    return pool.getconn()

def return_connection(conn):
    global pool
    if pool is not None:
        pool.putconn(conn)


def execute_query(sql, params=None, fetch=False, fetchone=False, commit=True):
    """
    Execute a SQL query with proper transaction handling.
    """
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            if fetchone:
                result = cur.fetchone()
            elif fetch:
                result = cur.fetchall()
            else:
                result = None

            if commit:
                logger.debug(f"Committing transaction for query: {sql}")
                conn.commit()

            return result
    except Exception as e:
        if conn and commit:
            logger.warning(f"Rolling back transaction due to error: {e}")
            conn.rollback()
        logger.error(f"Database error: {e}, SQL: {sql}, Params: {params}")
        raise
    finally:
        if conn:
            return_connection(conn)