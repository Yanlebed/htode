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
    def create_user(db: Session, user_data: dict) -> User:
        """Create a new user"""
        user = User(**user_data)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
