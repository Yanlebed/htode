# common/utils/db_utils.py

import logging
from typing import Optional
from common.db.database import execute_query
from common.db.models import Ad
from common.db.session import db_session

logger = logging.getLogger(__name__)


def get_ad_id_by_external_id(external_id: str) -> Optional[int]:
    with db_session() as db:
        ad = db.query(Ad).filter(Ad.external_id == external_id).first()
        return ad.id if ad else None


def ensure_ad_exists(ad_id: int) -> bool:
    try:
        with db_session() as db:
            exists = db.query(db.query(Ad).filter(Ad.id == ad_id).exists()).scalar()
            return exists
    except Exception as e:
        logger.error(f"Error checking if ad ID {ad_id} exists: {e}")
        return False