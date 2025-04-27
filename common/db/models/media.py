# common/db/models/media.py

from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from common.db.base import Base

class WhatsAppMedia(Base):
    """Model for WhatsApp media messages that need permanent storage"""
    __tablename__ = "whatsapp_media_messages"

    id = Column(Integer, primary_key=True, index=True)
    whatsapp_id = Column(String, index=True)  # Original user ID
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    media_url = Column(String, nullable=False)  # Original Twilio media URL
    permanent_url = Column(String, nullable=True)  # S3/CloudFront URL after transfer
    media_type = Column(String, nullable=False, default="image")  # image, video, audio, document
    processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    # Relationship (optional)
    user = relationship("User", back_populates="media_messages")