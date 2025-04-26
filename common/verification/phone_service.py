# common/verification/phone_service.py
import logging
from typing import Tuple, Optional, Dict, Any

from common.db.session import db_session
from common.db.repositories.verification_repository import VerificationRepository
from common.db.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


def create_verification_code(phone_number: str) -> str:
    """
    Create a verification code for a phone number

    Args:
        phone_number: Phone number to verify

    Returns:
        Generated verification code
    """
    with db_session() as db:
        return VerificationRepository.create_verification_code(db, phone_number)


def verify_code(phone_number: str, code: str) -> Tuple[bool, str]:
    """
    Verify a code for a phone number

    Args:
        phone_number: Phone number to verify
        code: Verification code to check

    Returns:
        Tuple of (success, error_message)
    """
    try:
        with db_session() as db:
            is_valid = VerificationRepository.verify_code(db, phone_number, code)

            if is_valid:
                return True, ""
            else:
                return False, "Неправильний код або термін дії коду закінчився"
    except Exception as e:
        logger.error(f"Error verifying code: {e}")
        return False, "Помилка при перевірці коду"


def get_user_by_phone(phone_number: str) -> Optional[Dict[str, Any]]:
    """
    Get user by phone number

    Args:
        phone_number: Phone number to look up

    Returns:
        User data dictionary or None if not found
    """
    try:
        with db_session() as db:
            user = UserRepository.get_by_phone(db, phone_number)

            if not user:
                return None

            return {
                "id": user.id,
                "telegram_id": user.telegram_id,
                "viber_id": user.viber_id,
                "whatsapp_id": user.whatsapp_id,
                "phone_number": user.phone_number,
                "email": user.email
            }
    except Exception as e:
        logger.error(f"Error getting user by phone: {e}")
        return None


def link_messenger_account(phone_number: str, messenger_type: str, messenger_id: str) -> Optional[int]:
    """
    Link a messenger account to a user with this phone number

    Args:
        phone_number: Phone number
        messenger_type: Type of messenger ("telegram", "viber", or "whatsapp")
        messenger_id: Messenger-specific ID

    Returns:
        User ID if successful, None otherwise
    """
    try:
        with db_session() as db:
            # Find user by phone
            user = UserRepository.get_by_phone(db, phone_number)

            if user:
                # Update messenger ID
                if messenger_type == "telegram":
                    user.telegram_id = messenger_id
                elif messenger_type == "viber":
                    user.viber_id = messenger_id
                elif messenger_type == "whatsapp":
                    user.whatsapp_id = messenger_id

                # Verify phone number if not already verified
                if not user.phone_verified:
                    user.phone_verified = True

                db.commit()
                return user.id
            else:
                # Create new user with phone and messenger ID
                user_data = {
                    "phone_number": phone_number,
                    "phone_verified": True
                }

                # Add messenger-specific ID
                user_data[f"{messenger_type}_id"] = messenger_id

                # Create user
                user = UserRepository.create_user(db, user_data)
                return user.id
    except Exception as e:
        logger.error(f"Error linking messenger account: {e}")
        return None


def transfer_subscriptions(from_user_id: int, to_user_id: int) -> bool:
    """
    Transfer subscriptions from one user to another

    Args:
        from_user_id: Source user ID
        to_user_id: Destination user ID

    Returns:
        True if successful, False otherwise
    """
    try:
        from common.db.repositories.subscription_repository import SubscriptionRepository

        with db_session() as db:
            return SubscriptionRepository.transfer_subscriptions(db, from_user_id, to_user_id)
    except Exception as e:
        logger.error(f"Error transferring subscriptions: {e}")
        return False