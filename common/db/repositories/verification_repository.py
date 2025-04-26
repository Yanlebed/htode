# common/db/repositories/verification_repository.py
from datetime import datetime, timedelta
import random
import string
from sqlalchemy.orm import Session
from common.db.models.verification import VerificationCode


class VerificationRepository:
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
        query = db.query(VerificationCode).filter(
            VerificationCode.expires_at <= datetime.now()
        )

        count = query.count()
        query.delete()
        db.commit()

        return count