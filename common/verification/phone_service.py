# common/verification/phone_service.py

import logging
import random
import string
from datetime import datetime, timedelta
from typing import Optional, Tuple

from common.db.database import execute_query
from common.db.models import User
from common.db.repositories.user_repository import UserRepository
from common.db.session import db_session

logger = logging.getLogger(__name__)

# Configuration
VERIFICATION_CODE_LENGTH = 6
VERIFICATION_CODE_EXPIRY_MINUTES = 10
MAX_VERIFICATION_ATTEMPTS = 3


def generate_verification_code() -> str:
    """Generate a random numeric verification code"""
    return ''.join(random.choices(string.digits, k=VERIFICATION_CODE_LENGTH))


def create_verification_code(phone_number: str) -> str:
    """
    Generate and store a verification code for a phone number.

    Args:
        phone_number: The phone number to verify

    Returns:
        The generated verification code
    """
    try:
        # Generate a random 6-digit code
        import random
        code = ''.join(random.choices('0123456789', k=6))

        # Store in database with expiration
        with db_session() as db:
            from datetime import datetime, timedelta
            from common.db.models.verification import VerificationCode

            # Check if there's an existing code and delete it
            existing = db.query(VerificationCode).filter(
                VerificationCode.phone_number == phone_number,
                VerificationCode.is_active == True
            ).first()

            if existing:
                existing.is_active = False

            # Create new verification code
            expiration = datetime.now() + timedelta(minutes=15)
            verification = VerificationCode(
                phone_number=phone_number,
                code=code,
                expires_at=expiration,
                is_active=True
            )

            db.add(verification)
            db.commit()

            return code
    except Exception as e:
        logger.error(f"Error creating verification code: {e}")
        # Generate code anyway so the flow can continue
        import random
        return ''.join(random.choices('0123456789', k=6))


# Verify code with improved implementation
def verify_code(phone_number: str, code: str) -> Tuple[bool, Optional[str]]:
    """
    Verify a code for a phone number.

    Args:
        phone_number: The phone number
        code: The verification code to check

    Returns:
        Tuple of (success, error_message)
    """
    try:
        with db_session() as db:
            from common.db.models.verification import VerificationCode
            from datetime import datetime

            # Find active verification code
            verification = db.query(VerificationCode).filter(
                VerificationCode.phone_number == phone_number,
                VerificationCode.code == code,
                VerificationCode.is_active == True,
                VerificationCode.expires_at > datetime.now()
            ).first()

            if not verification:
                return False, "Невірний код або закінчився термін дії коду"

            # Mark code as used
            verification.is_active = False
            db.commit()

            return True, None
    except Exception as e:
        logger.error(f"Error verifying code: {e}")
        return False, f"Помилка перевірки: {str(e)}"


def mark_phone_verified(phone_number: str) -> None:
    """
    Mark a phone number as verified in the users table

    Args:
        phone_number: The verified phone number
    """
    update_sql = """
                 UPDATE users
                 SET phone_verified = TRUE
                 WHERE phone_number = %s \
                 """
    execute_query(update_sql, [phone_number])

    logger.info(f"Marked phone number {phone_number} as verified")


def sanitize_phone_number(phone_number: str) -> str:
    """
    Sanitize a phone number to standard E.164 format

    Args:
        phone_number: Phone number in any format

    Returns:
        Sanitized phone number in E.164 format (e.g., +380991234567)
    """
    # Remove all non-digit characters except '+'
    clean_number = ''.join(c for c in phone_number if c.isdigit() or c == '+')

    # Ensure it starts with '+'
    if not clean_number.startswith('+'):
        clean_number = '+' + clean_number

    return clean_number


def link_messenger_account(phone_number, messenger_type, messenger_id):
    """
    Link a messenger account to a user with the provided phone number.

    Args:
        phone_number: User's phone number
        messenger_type: Type of messenger ("telegram", "viber", or "whatsapp")
        messenger_id: Messenger-specific ID

    Returns:
        User ID if successful, None otherwise
    """
    try:
        with db_session() as db:
            # First, find user by phone number
            user = UserRepository.get_by_phone(db, phone_number)

            if user:
                # Update the appropriate messenger ID
                if messenger_type == "telegram":
                    user.telegram_id = messenger_id
                elif messenger_type == "viber":
                    user.viber_id = messenger_id
                elif messenger_type == "whatsapp":
                    user.whatsapp_id = messenger_id

                db.commit()
                return user.id

            # No user with this phone, create a new one
            from datetime import datetime, timedelta
            free_until = datetime.now() + timedelta(days=7)

            # Create a new user with the provided messenger ID and phone number
            user_data = {
                "phone_number": phone_number,
                "phone_verified": True,
                "free_until": free_until
            }

            # Add the messenger ID to the user data
            if messenger_type == "telegram":
                user_data["telegram_id"] = messenger_id
            elif messenger_type == "viber":
                user_data["viber_id"] = messenger_id
            elif messenger_type == "whatsapp":
                user_data["whatsapp_id"] = messenger_id

            # Create the user
            user = User(**user_data)
            db.add(user)
            db.commit()

            return user.id
    except Exception as e:
        logger.error(f"Error linking messenger account: {e}")
        return None


def get_user_by_phone(phone_number):
    """
    Get user information by phone number.

    Args:
        phone_number: User's phone number

    Returns:
        User dictionary or None if not found
    """
    try:
        with db_session() as db:
            user = UserRepository.get_by_phone(db, phone_number)

            if user:
                # Convert to dictionary
                return {
                    "id": user.id,
                    "telegram_id": user.telegram_id,
                    "viber_id": user.viber_id,
                    "whatsapp_id": user.whatsapp_id,
                    "phone_number": user.phone_number,
                    "email": user.email,
                    "free_until": user.free_until.isoformat() if user.free_until else None,
                    "subscription_until": user.subscription_until.isoformat() if user.subscription_until else None
                }
            return None
    except Exception as e:
        logger.error(f"Error getting user by phone {phone_number}: {e}")
        return None


def transfer_subscriptions(source_user_id: int, target_user_id: int) -> bool:
    """
    Transfer subscriptions and other data from one user to another.
    Used when merging accounts.

    Args:
        source_user_id: Source user ID
        target_user_id: Target user ID

    Returns:
        True if successful, False otherwise
    """
    try:
        with db_session() as db:
            # 1. Transfer subscription filters that don't already exist
            from common.db.models.subscription import UserFilter
            from sqlalchemy import and_, not_, exists

            # Get source filters that don't exist in target
            source_filters = db.query(UserFilter).filter(
                UserFilter.user_id == source_user_id
            ).all()

            # Track how many were transferred
            transferred_filters = 0

            for source_filter in source_filters:
                # Check if similar filter exists in target
                existing = db.query(UserFilter).filter(
                    UserFilter.user_id == target_user_id,
                    UserFilter.property_type == source_filter.property_type,
                    UserFilter.city == source_filter.city,
                    UserFilter.price_min == source_filter.price_min,
                    UserFilter.price_max == source_filter.price_max
                ).first()

                if not existing:
                    # Create new filter for target user
                    new_filter = UserFilter(
                        user_id=target_user_id,
                        property_type=source_filter.property_type,
                        city=source_filter.city,
                        rooms_count=source_filter.rooms_count,
                        price_min=source_filter.price_min,
                        price_max=source_filter.price_max,
                        is_paused=source_filter.is_paused,
                        floor_max=source_filter.floor_max,
                        is_not_first_floor=source_filter.is_not_first_floor,
                        is_not_last_floor=source_filter.is_not_last_floor,
                        is_last_floor_only=source_filter.is_last_floor_only,
                        pets_allowed=source_filter.pets_allowed,
                        without_broker=source_filter.without_broker
                    )
                    db.add(new_filter)
                    transferred_filters += 1

            # 2. Transfer favorite ads that don't already exist
            from common.db.models.favorite import FavoriteAd

            source_favorites = db.query(FavoriteAd).filter(
                FavoriteAd.user_id == source_user_id
            ).all()

            transferred_favorites = 0

            for favorite in source_favorites:
                # Check if already exists
                existing = db.query(FavoriteAd).filter(
                    FavoriteAd.user_id == target_user_id,
                    FavoriteAd.ad_id == favorite.ad_id
                ).first()

                if not existing:
                    # Create new favorite for target user
                    new_favorite = FavoriteAd(
                        user_id=target_user_id,
                        ad_id=favorite.ad_id
                    )
                    db.add(new_favorite)
                    transferred_favorites += 1

            # 3. Extend subscription if source has longer subscription
            from common.db.models.user import User

            source_user = db.query(User).get(source_user_id)
            target_user = db.query(User).get(target_user_id)

            if source_user and target_user:
                # Transfer free subscription if source has longer one
                if (source_user.free_until and
                        (not target_user.free_until or source_user.free_until > target_user.free_until)):
                    target_user.free_until = source_user.free_until

                # Transfer paid subscription if source has longer one
                if (source_user.subscription_until and
                        (
                                not target_user.subscription_until or source_user.subscription_until > target_user.subscription_until)):
                    target_user.subscription_until = source_user.subscription_until

            # Commit all changes
            db.commit()

            # Invalidate cache
            from common.utils.cache import redis_client

            redis_client.delete(f"user_filters:{target_user_id}")
            redis_client.delete(f"user_favorites:{target_user_id}")
            redis_client.delete(f"user_subscription:{target_user_id}")
            redis_client.delete(f"subscription_status:{target_user_id}")

            logger.info(
                f"Transferred {transferred_filters} filters and {transferred_favorites} favorites from user {source_user_id} to {target_user_id}")
            return True

    except Exception as e:
        logger.error(f"Error transferring subscriptions: {e}")
        return False