# common/verification/phone_service.py

import logging
import random
import string
from datetime import datetime, timedelta
from typing import Optional, Tuple

from common.db.database import execute_query

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
    Create a new verification code for the given phone number.

    Args:
        phone_number: The phone number to create a code for

    Returns:
        The generated verification code
    """
    # Sanitize phone number
    phone_number = sanitize_phone_number(phone_number)

    # Generate a new code
    code = generate_verification_code()
    expires_at = datetime.now() + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES)

    # Delete any existing codes for this number
    delete_sql = "DELETE FROM verification_codes WHERE phone_number = %s"
    execute_query(delete_sql, [phone_number])

    # Insert the new code
    insert_sql = """
                 INSERT INTO verification_codes (phone_number, code, expires_at)
                 VALUES (%s, %s, %s) \
                 """
    execute_query(insert_sql, [phone_number, code, expires_at])

    # Send the code via SMS (for production)
    from common.verification.sms_service import send_verification_code
    send_verification_code(phone_number, code)

    logger.info(f"Created verification code for {phone_number}")
    return code


def verify_code(phone_number: str, code: str) -> Tuple[bool, Optional[str]]:
    """
    Verify a code for a phone number.

    Args:
        phone_number: The phone number to verify
        code: The verification code

    Returns:
        Tuple of (success, error_message)
    """
    # Sanitize phone number
    phone_number = sanitize_phone_number(phone_number)

    # Get the verification record
    select_sql = """
                 SELECT id, code, expires_at, attempts
                 FROM verification_codes
                 WHERE phone_number = %s \
                 """
    record = execute_query(select_sql, [phone_number], fetchone=True)

    if not record:
        return False, "No verification code found for this number"

    # Check if expired
    if datetime.now() > record['expires_at']:
        return False, "Verification code has expired"

    # Check if too many attempts
    if record['attempts'] >= MAX_VERIFICATION_ATTEMPTS:
        return False, "Too many verification attempts"

    # Increment attempt counter
    update_sql = """
                 UPDATE verification_codes
                 SET attempts = attempts + 1
                 WHERE id = %s \
                 """
    execute_query(update_sql, [record['id']])

    # Check if code matches
    if record['code'] != code:
        return False, "Invalid verification code"

    # Code is valid, mark phone as verified
    mark_phone_verified(phone_number)

    # Delete the verification record
    delete_sql = "DELETE FROM verification_codes WHERE id = %s"
    execute_query(delete_sql, [record['id']])

    return True, None


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


def link_messenger_account(phone_number: str, messenger_type: str, messenger_id: str) -> int:
    """
    Link a messenger account to a user with the given phone number.
    If user with phone doesn't exist, creates a new user.

    Args:
        phone_number: The verified phone number
        messenger_type: "telegram", "viber", or "whatsapp"
        messenger_id: The ID of the user in that messenger platform

    Returns:
        The user's database ID
    """
    # Sanitize phone number
    phone_number = sanitize_phone_number(phone_number)

    # Check if user with this phone exists
    select_sql = "SELECT id FROM users WHERE phone_number = %s"
    user = execute_query(select_sql, [phone_number], fetchone=True)

    if user:
        # Update the existing user with the new messenger ID
        if messenger_type == "telegram":
            update_sql = "UPDATE users SET telegram_id = %s WHERE id = %s"
        elif messenger_type == "viber":
            update_sql = "UPDATE users SET viber_id = %s WHERE id = %s"
        elif messenger_type == "whatsapp":
            update_sql = "UPDATE users SET whatsapp_id = %s WHERE id = %s"
        else:
            raise ValueError(f"Invalid messenger type: {messenger_type}")

        execute_query(update_sql, [messenger_id, user['id']])
        logger.info(f"Linked {messenger_type} account {messenger_id} to existing user {user['id']}")
        return user['id']
    else:
        # Create a new user with this phone number and messenger ID
        free_until = (datetime.now() + timedelta(days=7)).isoformat()

        if messenger_type == "telegram":
            insert_sql = """
                         INSERT INTO users (phone_number, phone_verified, telegram_id, free_until)
                         VALUES (%s, TRUE, %s, %s) RETURNING id \
                         """
        elif messenger_type == "viber":
            insert_sql = """
                         INSERT INTO users (phone_number, phone_verified, viber_id, free_until)
                         VALUES (%s, TRUE, %s, %s) RETURNING id \
                         """
        elif messenger_type == "whatsapp":
            insert_sql = """
                         INSERT INTO users (phone_number, phone_verified, whatsapp_id, free_until)
                         VALUES (%s, TRUE, %s, %s) RETURNING id \
                         """
        else:
            raise ValueError(f"Invalid messenger type: {messenger_type}")

        user = execute_query(insert_sql, [phone_number, messenger_id, free_until], fetchone=True, commit=True)
        logger.info(f"Created new user with {messenger_type} account {messenger_id}")
        return user['id']


def get_user_by_phone(phone_number: str) -> Optional[dict]:
    """
    Get user by phone number

    Args:
        phone_number: Phone number to look up

    Returns:
        User dict or None if not found
    """
    phone_number = sanitize_phone_number(phone_number)

    sql = """
          SELECT id, \
                 telegram_id, \
                 viber_id, \
                 whatsapp_id, \
                 phone_number, \
                 phone_verified,
                 free_until, \
                 subscription_until
          FROM users
          WHERE phone_number = %s \
          """

    return execute_query(sql, [phone_number], fetchone=True)


def transfer_subscriptions(source_user_id: int, target_user_id: int) -> None:
    """
    Transfer all subscriptions from source user to target user.
    Used when merging accounts from different platforms.

    Args:
        source_user_id: The user ID to transfer from
        target_user_id: The user ID to transfer to
    """
    # First, get all source user's filters
    select_sql = """
                 SELECT property_type, city, rooms_count, price_min, price_max, is_paused
                 FROM user_filters
                 WHERE user_id = %s \
                 """
    filters = execute_query(select_sql, [source_user_id], fetch=True)

    if not filters:
        logger.info(f"No filters to transfer from user {source_user_id}")
        return

    # Insert filters for target user
    for filter_data in filters:
        insert_sql = """
                     INSERT INTO user_filters
                     (user_id, property_type, city, rooms_count, price_min, price_max, is_paused)
                     VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (user_id) DO NOTHING \
                     """
        execute_query(
            insert_sql,
            [
                target_user_id,
                filter_data['property_type'],
                filter_data['city'],
                filter_data['rooms_count'],
                filter_data['price_min'],
                filter_data['price_max'],
                filter_data['is_paused']
            ]
        )

    # Transfer favorites
    transfer_sql = """
                   INSERT INTO favorite_ads (user_id, ad_id)
                   SELECT %s, ad_id \
                   FROM favorite_ads
                   WHERE user_id = %s ON CONFLICT (user_id, ad_id) DO NOTHING \
                   """
    execute_query(transfer_sql, [target_user_id, source_user_id])

    # Transfer subscription period if longer
    update_sql = """
                 UPDATE users
                 SET subscription_until =
                         CASE
                             WHEN (SELECT subscription_until FROM users WHERE id = %s) > subscription_until
                                 THEN (SELECT subscription_until FROM users WHERE id = %s)
                             ELSE subscription_until
                             END,
                     free_until         =
                         CASE
                             WHEN (SELECT free_until FROM users WHERE id = %s) > free_until
                                 THEN (SELECT free_until FROM users WHERE id = %s)
                             ELSE free_until
                             END
                 WHERE id = %s \
                 """
    execute_query(update_sql, [
        source_user_id, source_user_id,
        source_user_id, source_user_id,
        target_user_id
    ])

    logger.info(f"Transferred subscriptions from user {source_user_id} to {target_user_id}")