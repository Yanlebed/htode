# common/db/repositories/user_repository.py
from datetime import datetime, timedelta
from typing import List, Optional, Union, Dict, Any

from sqlalchemy.orm import Session

from common.db.models.user import User
from common.utils.cache import redis_cache, redis_client, CacheTTL


class UserRepository:
    """Repository for user operations"""

    @staticmethod
    def get_by_id(db: Session, user_id: int) -> Optional[User]:
        """Get user by database ID"""
        return db.query(User).filter(User.id == user_id).first()

    @staticmethod
    def get_by_messenger_id(
            db: Session, messenger_id: str, messenger_type: str = "telegram"
    ) -> Optional[User]:
        """Get user by messenger ID"""
        filter_kwargs = {f"{messenger_type}_id": messenger_id}
        return db.query(User).filter_by(**filter_kwargs).first()

    @staticmethod
    def get_by_phone(db: Session, phone_number: str) -> Optional[User]:
        """Get user by phone number"""
        return db.query(User).filter(User.phone_number == phone_number).first()

    @staticmethod
    def get_by_email(db: Session, email: str) -> Optional[User]:
        """Get user by email"""
        return db.query(User).filter(User.email == email.lower()).first()

    @staticmethod
    def get_or_create(
            db: Session, messenger_id: str, messenger_type: str = "telegram"
    ) -> User:
        """Get or create a user with messenger ID"""
        return User.get_or_create(db, messenger_id, messenger_type)

    @staticmethod
    def start_free_subscription(db: Session, user_id: int) -> bool:
        """Start a free subscription for the user"""
        user = UserRepository.get_by_id(db, user_id)
        if not user:
            return False

        user.free_until = datetime.now() + timedelta(days=7)
        db.commit()

        # Invalidate cache
        redis_client.delete(f"user_subscription:{user_id}")
        return True

    @staticmethod
    @redis_cache("subscription_status", ttl=CacheTTL.MEDIUM)
    def get_subscription_status(db: Session, user_id: int) -> Dict[str, Any]:
        """Get subscription status for a user with caching"""
        user = UserRepository.get_by_id(db, user_id)
        if not user:
            return {"active": False}

        now = datetime.now()
        free_active = user.free_until and user.free_until > now
        paid_active = user.subscription_until and user.subscription_until > now

        return {
            "active": free_active or paid_active,
            "free_active": free_active,
            "paid_active": paid_active,
            "free_until": user.free_until.isoformat() if user.free_until else None,
            "subscription_until": user.subscription_until.isoformat() if user.subscription_until else None
        }

    @staticmethod
    def update_last_active(db: Session, user_id: int) -> bool:
        """Update the user's last active timestamp"""
        user = UserRepository.get_by_id(db, user_id)
        if not user:
            return False

        user.last_active = datetime.now()
        db.commit()
        return True

    @staticmethod
    def create_messenger_user(
            db: Session, messenger_id: str, messenger_type: str, free_until: datetime
    ) -> User:
        """Create a new user with messenger ID"""
        messenger_field = f"{messenger_type}_id"
        user_data = {
            messenger_field: messenger_id,
            "free_until": free_until
        }
        user = User(**user_data)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user

    @staticmethod
    def update_messenger_id(
            db: Session, user_id: int, messenger_id: str, messenger_type: str
    ) -> bool:
        """Update/set a messenger ID for a user"""
        user = UserRepository.get_by_id(db, user_id)
        if not user:
            return False

        setattr(user, f"{messenger_type}_id", messenger_id)
        db.commit()
        return True

    @staticmethod
    def link_phone_number(
            db: Session, user_id: int, phone_number: str, verified: bool = False
    ) -> bool:
        """Link a phone number to a user"""
        user = UserRepository.get_by_id(db, user_id)
        if not user:
            return False

        user.phone_number = phone_number
        user.phone_verified = verified
        db.commit()
        return True

    @staticmethod
    def get_users_with_expiring_subscription(db: Session, days: int) -> List[User]:
        """
        Get users whose subscription is expiring in the specified number of days.

        Args:
            db: Database session
            days: Number of days until expiration

        Returns:
            List of User objects
        """
        future_date = datetime.now() + timedelta(days=days, hours=1)
        past_date = datetime.now() + timedelta(days=days - 1)

        return db.query(User).filter(
            User.subscription_until.isnot(None),
            User.subscription_until > datetime.now(),
            User.subscription_until < future_date,
            User.subscription_until > past_date
        ).all()

    @staticmethod
    def get_active_users(db: Session, days: int = 7, limit: int = 100) -> List[User]:
        """
        Get users who have been active within the specified number of days.

        Args:
            db: Database session
            days: Number of days to consider as active
            limit: Maximum number of users to return

        Returns:
            List of User objects
        """
        cutoff_date = datetime.now() - timedelta(days=days)
        return db.query(User).filter(
            User.last_active > cutoff_date
        ).limit(limit).all()

    @staticmethod
    def update_subscription_end_date(
            db: Session, user_id: int, subscription_until: datetime
    ) -> bool:
        """Update user subscription end date"""
        user = UserRepository.get_by_id(db, user_id)
        if not user:
            return False

        user.subscription_until = subscription_until
        db.commit()
        return True

    @staticmethod
    def get_user_id_by_telegram_id(db: Session, telegram_id: str) -> Optional[int]:
        """Get database user ID from Telegram ID"""
        user = db.query(User).filter(User.telegram_id == telegram_id).first()
        return user.id if user else None

    @staticmethod
    def get_subscription_until(db: Session, user_id: int, free: bool = False) -> Optional[str]:
        """Get subscription expiration date for a user"""
        user = db.query(User).filter(User.id == user_id).first()

        if not user:
            return None

        # Get the appropriate date field
        date_field = user.free_until if free else user.subscription_until

        if date_field:
            return date_field.strftime("%d.%m.%Y")
        return None