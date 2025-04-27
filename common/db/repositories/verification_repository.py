# common/db/repositories/verification_repository.py

from datetime import datetime, timedelta
import random
import string
from typing import Optional
from sqlalchemy.orm import Session

from common.db.models.verification import VerificationCode
from common.db.repositories.base_repository import BaseRepository


class VerificationRepository(BaseRepository):
    """Repository for verification operations"""

    @staticmethod
    def create_verification_code(db: Session, phone_number: str, user_id: int = None) -> str:
        """Create a verification code for a phone number"""
        # Generate random 6-digit code
        code = ''.join(random.choices(string.digits, k=6))

        # Set expiration time (e.g., 10 minutes)
        expires_at = datetime.now() + timedelta(minutes=10)

        # Create verification code
        verification_code = VerificationCode(
            user_id=user_id,
            phone_number=phone_number,
            code=code,
            expires_at=expires_at
        )

        db.add(verification_code)
        db.commit()

        return code

    @staticmethod
    def verify_code(db: Session, phone_number: str, code: str) -> bool:
        """Verify a code for a phone number"""
        verification = db.query(VerificationCode).filter(
            VerificationCode.phone_number == phone_number,
            VerificationCode.code == code,
            VerificationCode.expires_at > datetime.now()
        ).first()

        return verification is not None

    @staticmethod
    def cleanup_expired_codes(db: Session) -> int:
        """Clean up expired verification codes"""
        result = db.query(VerificationCode).filter(
            VerificationCode.expires_at <= datetime.now()
        ).delete()

        db.commit()
        return result

    @staticmethod
    def get_recent_verification_attempts(db: Session, phone_number: str, minutes: int = 30) -> int:
        """Count recent verification attempts for a phone number"""
        time_threshold = datetime.now() - timedelta(minutes=minutes)

        return db.query(VerificationCode).filter(
            VerificationCode.phone_number == phone_number,
            VerificationCode.created_at >= time_threshold
        ).count()

    @staticmethod
    def get_by_phone_and_code(db: Session, phone_number: str, code: str) -> Optional[VerificationCode]:
        """Get verification record by phone and code"""
        return db.query(VerificationCode).filter(
            VerificationCode.phone_number == phone_number,
            VerificationCode.code == code
        ).first()