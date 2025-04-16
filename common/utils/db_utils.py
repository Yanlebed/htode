# Create this new file: common/utils/db_utils.py

import logging
from typing import Optional, Dict, Any
from common.db.database import execute_query

logger = logging.getLogger(__name__)


def get_ad_id_by_external_id(external_id: str) -> Optional[int]:
    """
    Safely retrieve the database ID for an ad using its external ID.

    Args:
        external_id: The external/source ID of the ad

    Returns:
        The database ID if found, None otherwise
    """
    try:
        sql = "SELECT id FROM ads WHERE external_id = %s"
        row = execute_query(sql, [external_id], fetchone=True)
        return row["id"] if row else None
    except Exception as e:
        logger.error(f"Error retrieving ad ID for external_id={external_id}: {e}")
        return None


def ensure_ad_exists(ad_id: int) -> bool:
    """
    Check if an ad with the given ID exists in the database.

    Args:
        ad_id: The database ID to check

    Returns:
        True if the ad exists, False otherwise
    """
    try:
        sql = "SELECT 1 FROM ads WHERE id = %s"
        row = execute_query(sql, [ad_id], fetchone=True)
        return bool(row)
    except Exception as e:
        logger.error(f"Error checking if ad ID {ad_id} exists: {e}")
        return False