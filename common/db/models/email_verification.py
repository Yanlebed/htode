# common/db/models/email_verification.py
from sqlalchemy import Column, Integer, String, DateTime
from datetime import datetime

from common.db.base import Base

class EmailVerificationToken(Base):
    __tablename__ = "email_verification_tokens"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, nullable=False, index=True)
    token = Column(String, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.now)