# common/db/query_builder.py
"""
Query builder utility to build complex queries and prevent N+1 problems
"""
import logging
from typing import List, Dict, Any, Optional, Tuple, Union

from .database import execute_query

logger = logging.getLogger(__name__)


class QueryBuilder:
    """
    A simple query builder to construct SQL queries with proper parameter handling
    """

    def __init__(self, table_name):
        self.table_name = table_name
        self.select_columns = ["*"]
        self.where_clauses = []
        self.where_params = []
        self.order_by = []
        self.group_by = []
        self.limit_val = None
        self.offset_val = None
        self.joins = []

    def select(self, *columns):
        """Set specific columns to select"""
        if columns:
            self.select_columns = columns
        return self

    def where(self, clause, *params):
        """Add WHERE clause with parameters"""
        self.where_clauses.append(clause)
        self.where_params.extend(params)
        return self

    def where_in(self, column, values):
        """Add WHERE IN clause for batch operations"""
        if not values:
            # This ensures the query always has valid SQL syntax even with empty values
            self.where_clauses.append("FALSE")
            return self

        self.where_clauses.append(f"{column} IN %s")
        self.where_params.append(tuple(values))
        return self

    def order_by_field(self, field, direction="ASC"):
        """Add ORDER BY clause"""
        self.order_by.append(f"{field} {direction}")
        return self

    def group_by_field(self, *fields):
        """Add GROUP BY clause"""
        self.group_by.extend(fields)
        return self

    def limit(self, limit_value):
        """Add LIMIT clause"""
        self.limit_val = limit_value
        return self

    def offset(self, offset_value):
        """Add OFFSET clause"""
        self.offset_val = offset_value
        return self

    def join(self, table, condition, join_type="INNER"):
        """Add JOIN clause"""
        self.joins.append(f"{join_type} JOIN {table} ON {condition}")
        return self

    def build(self):
        """Build the final SQL query and parameters"""
        sql = f"SELECT {', '.join(self.select_columns)} FROM {self.table_name}"

        # Add joins
        if self.joins:
            sql += " " + " ".join(self.joins)

        # Add where clauses
        if self.where_clauses:
            sql += " WHERE " + " AND ".join(self.where_clauses)

        # Add group by
        if self.group_by:
            sql += " GROUP BY " + ", ".join(self.group_by)

        # Add order by
        if self.order_by:
            sql += " ORDER BY " + ", ".join(self.order_by)

        # Add limit and offset
        if self.limit_val is not None:
            sql += f" LIMIT {self.limit_val}"

        if self.offset_val is not None:
            sql += f" OFFSET {self.offset_val}"

        return sql, self.where_params

    def execute(self, fetch=True, fetchone=False):
        """Execute the query and return results"""
        sql, params = self.build()
        logger.debug(f"Executing query: {sql} with params {params}")
        return execute_query(sql, params, fetch=fetch, fetchone=fetchone)