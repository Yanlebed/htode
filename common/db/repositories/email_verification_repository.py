# common/db/repositories/email_verification_repository.py

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from common.db.models.email_verification import EmailVerificationToken
from common.db.models.user import User


class EmailVerificationRepository:
    @staticmethod
    def create_token(db: Session, email: str, token: str, expires_at: datetime) -> EmailVerificationToken:
        """Create a verification token for an email"""
        # Delete any existing tokens for this email
        db.query(EmailVerificationToken).filter(EmailVerificationToken.email == email).delete()

        # Create a new token
        token_record = EmailVerificationToken(
            email=email,
            token=token,
            expires_at=expires_at,
            attempts=0
        )
        db.add(token_record)
        db.commit()
        db.refresh(token_record)
        return token_record

    @staticmethod
    def get_token(db: Session, email: str) -> Optional[EmailVerificationToken]:
        """Get token record for an email"""
        return db.query(EmailVerificationToken).filter(EmailVerificationToken.email == email).first()

    @staticmethod
    def increment_attempts(db: Session, token_id: int) -> int:
        """Increment the attempts counter for a token"""
        token = db.query(EmailVerificationToken).get(token_id)
        if token:
            token.attempts += 1
            db.commit()
            return token.attempts
        return 0

    @staticmethod
    def verify_token(db: Session, email: str, token: str) -> bool:
        """Verify a token for an email"""
        token_record = db.query(EmailVerificationToken).filter(
            EmailVerificationToken.email == email,
            EmailVerificationToken.token == token,
            EmailVerificationToken.expires_at > datetime.now()
        ).first()

        if not token_record:
            return False

        # Increment attempt counter
        EmailVerificationRepository.increment_attempts(db, token_record.id)

        return token_record.attempts <= 3  # Maximum 3 attempts

    @staticmethod
    def delete_token(db: Session, email: str) -> bool:
        """Delete verification token for an email"""
        result = db.query(EmailVerificationToken).filter(EmailVerificationToken.email == email).delete()
        db.commit()
        return result > 0

    @staticmethod
    def mark_email_verified(db: Session, email: str) -> bool:
        """Mark a user's email as verified"""
        user = db.query(User).filter(User.email == email).first()
        if user:
            user.email_verified = True
            db.commit()
            return True
        return False