# common/db/repositories/verification_repository.py

from datetime import datetime, timedelta
import random
import string
from typing import Optional
from sqlalchemy.orm import Session

from common.db.models.verification import VerificationCode
from common.db.repositories.base_repository import BaseRepository
from common.utils.logging_config import log_operation, log_context

# Import the repository logger
from . import logger


class VerificationRepository(BaseRepository):
    """Repository for verification operations"""

    @staticmethod
    @log_operation("create_verification_code")
    def create_verification_code(db: Session, phone_number: str, user_id: int = None) -> str:
        """Create a verification code for a phone number"""
        with log_context(logger, phone_number=phone_number[:5] + "...", user_id=user_id):
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

            logger.info("Created verification code", extra={
                'phone_number': phone_number[:5] + "...",
                'user_id': user_id,
                'expires_at': expires_at.isoformat()
            })

            return code

    @staticmethod
    @log_operation("verify_code")
    def verify_code(db: Session, phone_number: str, code: str) -> bool:
        """Verify a code for a phone number"""
        with log_context(logger, phone_number=phone_number[:5] + "..."):
            verification = db.query(VerificationCode).filter(
                VerificationCode.phone_number == phone_number,
                VerificationCode.code == code,
                VerificationCode.expires_at > datetime.now()
            ).first()

            result = verification is not None

            logger.info("Code verification attempt", extra={
                'phone_number': phone_number[:5] + "...",
                'success': result
            })

            return result

    @staticmethod
    @log_operation("cleanup_expired_codes")
    def cleanup_expired_codes(db: Session) -> int:
        """Clean up expired verification codes"""
        with log_context(logger):
            result = db.query(VerificationCode).filter(
                VerificationCode.expires_at <= datetime.now()
            ).delete()

            db.commit()

            logger.info("Cleaned up expired verification codes", extra={
                'deleted_count': result
            })

            return result

    @staticmethod
    @log_operation("get_recent_verification_attempts")
    def get_recent_verification_attempts(db: Session, phone_number: str, minutes: int = 30) -> int:
        """Count recent verification attempts for a phone number"""
        with log_context(logger, phone_number=phone_number[:5] + "...", minutes=minutes):
            time_threshold = datetime.now() - timedelta(minutes=minutes)

            count = db.query(VerificationCode).filter(
                VerificationCode.phone_number == phone_number,
                VerificationCode.created_at >= time_threshold
            ).count()

            logger.debug("Counted recent verification attempts", extra={
                'phone_number': phone_number[:5] + "...",
                'minutes': minutes,
                'attempt_count': count
            })

            return count

    @staticmethod
    @log_operation("get_by_phone_and_code")
    def get_by_phone_and_code(db: Session, phone_number: str, code: str) -> Optional[VerificationCode]:
        """Get verification record by phone and code"""
        with log_context(logger, phone_number=phone_number[:5] + "..."):
            verification = db.query(VerificationCode).filter(
                VerificationCode.phone_number == phone_number,
                VerificationCode.code == code
            ).first()

            if verification:
                logger.debug("Found verification record", extra={
                    'phone_number': phone_number[:5] + "...",
                    'expires_at': verification.expires_at.isoformat()
                })
            else:
                logger.debug("Verification record not found", extra={
                    'phone_number': phone_number[:5] + "..."
                })

            return verification