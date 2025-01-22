# common/db/database.py

import psycopg2
from psycopg2.extras import RealDictCursor
from common.config import DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASS

def get_connection():
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASS
    )

def execute_query(sql, params=None, fetch=False, fetchone=False):
    with get_connection() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            if fetchone:
                return cur.fetchone()
            if fetch:
                return cur.fetchall()
            conn.commit()
