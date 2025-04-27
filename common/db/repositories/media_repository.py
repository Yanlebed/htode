# common/db/repositories/media_repository.py
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy import desc
from sqlalchemy.orm import Session
from common.db.models.media import WhatsAppMedia
from common.db.repositories.base_repository import BaseRepository


class MediaRepository(BaseRepository):
    """Repository for media operations"""

    @staticmethod
    def create_media_record(db: Session, data: Dict[str, Any]) -> WhatsAppMedia:
        """Create a new media record"""
        media = WhatsAppMedia(**data)
        db.add(media)
        db.commit()
        db.refresh(media)
        return media

    @staticmethod
    def get_unprocessed_media(db: Session, limit: int = 50) -> List[WhatsAppMedia]:
        """Get unprocessed media records"""
        return db.query(WhatsAppMedia).filter(
            WhatsAppMedia.processed == False
        ).order_by(desc(WhatsAppMedia.created_at)).limit(limit).all()

    @staticmethod
    def update_media_status(db: Session, media_id: int, permanent_url: str, processed: bool = True) -> Optional[
        WhatsAppMedia]:
        """Update media status after processing"""
        media = db.query(WhatsAppMedia).get(media_id)
        if media:
            media.permanent_url = permanent_url
            media.processed = processed
            media.updated_at = datetime.now()
            db.commit()
            db.refresh(media)
        return media

    @staticmethod
    def get_user_media(db: Session, user_id: int, media_type: Optional[str] = None, limit: int = 20) -> List[
        WhatsAppMedia]:
        """Get media records for a user"""
        query = db.query(WhatsAppMedia).filter(WhatsAppMedia.user_id == user_id)

        if media_type:
            query = query.filter(WhatsAppMedia.media_type == media_type)

        return query.order_by(desc(WhatsAppMedia.created_at)).limit(limit).all()

    @staticmethod
    def cleanup_old_media(db: Session, days: int = 90) -> int:
        """Remove old processed media records"""
        cutoff_date = datetime.now() - timedelta(days=days)
        result = db.query(WhatsAppMedia).filter(
            WhatsAppMedia.processed == True,
            WhatsAppMedia.created_at < cutoff_date
        ).delete()

        db.commit()
        return result