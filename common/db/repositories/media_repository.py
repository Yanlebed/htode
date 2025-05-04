# common/db/repositories/media_repository.py

from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import desc
from sqlalchemy.orm import Session

from common.db.models.media import WhatsAppMedia
from common.db.repositories.base_repository import BaseRepository
from common.utils.logging_config import log_operation, log_context, LogAggregator

# Import the repository logger
from . import logger


class MediaRepository(BaseRepository):
    """Repository for media operations"""

    @staticmethod
    @log_operation("create_media_record")
    def create_media_record(db: Session, data: Dict[str, Any]) -> WhatsAppMedia:
        """Create a new media record"""
        with log_context(logger, media_type=data.get('media_type'), user_id=data.get('user_id')):
            media = WhatsAppMedia(**data)
            db.add(media)
            db.commit()
            db.refresh(media)

            logger.info("Created media record", extra={
                'media_id': media.id,
                'media_type': media.media_type,
                'user_id': media.user_id,
                'whatsapp_id': media.whatsapp_id
            })

            return media

    @staticmethod
    @log_operation("get_unprocessed_media")
    def get_unprocessed_media(db: Session, limit: int = 50) -> List[WhatsAppMedia]:
        """Get unprocessed media records"""
        with log_context(logger, limit=limit):
            try:
                media_records = db.query(WhatsAppMedia) \
                    .filter(WhatsAppMedia.processed == False) \
                    .order_by(desc(WhatsAppMedia.created_at)) \
                    .limit(limit) \
                    .all()

                logger.debug("Retrieved unprocessed media", extra={
                    'limit': limit,
                    'found_count': len(media_records)
                })

                return media_records
            except Exception as e:
                logger.error("Error getting unprocessed media", exc_info=True, extra={
                    'limit': limit,
                    'error_type': type(e).__name__
                })
                return []

    @staticmethod
    @log_operation("update_media_status")
    def update_media_status(db: Session, media_id: int, permanent_url: str, processed: bool = True) -> Optional[
        WhatsAppMedia]:
        """Update media status after processing"""
        with log_context(logger, media_id=media_id, processed=processed):
            media = db.query(WhatsAppMedia).get(media_id)
            if media:
                media.permanent_url = permanent_url
                media.processed = processed
                media.updated_at = datetime.now()
                db.commit()
                db.refresh(media)

                logger.info("Updated media status", extra={
                    'media_id': media_id,
                    'processed': processed,
                    'has_permanent_url': bool(permanent_url)
                })
            else:
                logger.warning("Media not found for status update", extra={'media_id': media_id})

            return media

    @staticmethod
    @log_operation("get_user_media")
    def get_user_media(db: Session, user_id: int, media_type: Optional[str] = None, limit: int = 20) -> List[
        WhatsAppMedia]:
        """Get media records for a user"""
        with log_context(logger, user_id=user_id, media_type=media_type, limit=limit):
            query = db.query(WhatsAppMedia).filter(WhatsAppMedia.user_id == user_id)

            if media_type:
                query = query.filter(WhatsAppMedia.media_type == media_type)

            media_records = query.order_by(desc(WhatsAppMedia.created_at)).limit(limit).all()

            logger.debug("Retrieved user media", extra={
                'user_id': user_id,
                'media_type': media_type,
                'limit': limit,
                'found_count': len(media_records)
            })

            return media_records

    @staticmethod
    @log_operation("cleanup_old_media")
    def cleanup_old_media(db: Session, days: int = 90) -> int:
        """Remove old processed media records"""
        with log_context(logger, days=days):
            cutoff_date = datetime.now() - timedelta(days=days)
            result = db.query(WhatsAppMedia).filter(
                WhatsAppMedia.processed == True,
                WhatsAppMedia.created_at < cutoff_date
            ).delete()

            db.commit()

            logger.info("Cleaned up old media", extra={
                'days_old': days,
                'cutoff_date': cutoff_date.isoformat(),
                'deleted_count': result
            })

            return result