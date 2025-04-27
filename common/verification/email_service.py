# common/verification/email_service.py

import logging
import smtplib
import uuid
import os
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from common.db.session import db_session
from common.db.repositories.email_verification_repository import EmailVerificationRepository
from common.db.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)

# Configuration
EMAIL_VERIFICATION_EXPIRY_MINUTES = 30
MAX_VERIFICATION_ATTEMPTS = 3
EMAIL_SERVICE_ENABLED = os.getenv("EMAIL_SERVICE_ENABLED", "false").lower() == "true"
EMAIL_SERVICE_DEBUG = os.getenv("EMAIL_SERVICE_DEBUG", "false").lower() == "true"

# SMTP settings
SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
FROM_EMAIL = os.getenv("FROM_EMAIL", "noreply@realestatefinder.com")


def generate_verification_token():
    """Generate a unique verification token"""
    return str(uuid.uuid4())


def create_verification_token(email):
    """
    Create a verification token for the given email

    Returns:
        The verification token
    """
    # Normalize email
    email = email.lower().strip()

    # Generate token
    token = generate_verification_token()
    expires_at = datetime.now() + timedelta(minutes=EMAIL_VERIFICATION_EXPIRY_MINUTES)

    with db_session() as db:
        # Create token using repository
        EmailVerificationRepository.create_token(db, email, token, expires_at)

    # Send verification email
    send_verification_email(email, token)

    logger.info(f"Created verification token for {email}")
    return token


def verify_token(email, token):
    """
    Verify the token for an email address

    Returns:
        (success, error_message) tuple
    """
    # Normalize email
    email = email.lower().strip()

    with db_session() as db:
        # Get the verification record
        token_record = EmailVerificationRepository.get_token(db, email)

        if not token_record:
            return False, "No verification token found for this email"

        # Check if expired
        if datetime.now() > token_record.expires_at:
            return False, "Verification token has expired"

        # Check attempts
        if token_record.attempts >= MAX_VERIFICATION_ATTEMPTS:
            return False, "Too many verification attempts"

        # Verify token
        if not EmailVerificationRepository.verify_token(db, email, token):
            return False, "Invalid verification token"

        # Mark email as verified
        EmailVerificationRepository.mark_email_verified(db, email)

        # Delete the token
        EmailVerificationRepository.delete_token(db, email)

        return True, None


def mark_email_verified(email):
    """Mark an email as verified"""
    with db_session() as db:
        EmailVerificationRepository.mark_email_verified(db, email)
        logger.info(f"Marked email {email} as verified")


def send_verification_email(email, token):
    """Send verification email with a token"""
    if not EMAIL_SERVICE_ENABLED:
        # For development, just log the token
        logger.info(f"EMAIL SERVICE DISABLED. Would send token {token} to {email}")

        # Write to the file in debug mode
        if EMAIL_SERVICE_DEBUG:
            try:
                with open(f"email_token_{email.replace('@', '_at_')}.txt", "w") as f:
                    f.write(token)
            except Exception as e:
                logger.error(f"Failed to write debug email token to file: {e}")

        return True

    try:
        # Create a message
        msg = MIMEMultipart()
        msg['From'] = FROM_EMAIL
        msg['To'] = email
        msg['Subject'] = "Verify your email for RealEstateFinder"

        # Message body
        body = f"""
        <html>
        <body>
            <h2>Email Verification</h2>
            <p>Thank you for using RealEstateFinder!</p>
            <p>Your verification code is: <strong>{token}</strong></p>
            <p>This code will expire in {EMAIL_VERIFICATION_EXPIRY_MINUTES} minutes.</p>
            <p>If you didn't request this verification, please ignore this email.</p>
        </body>
        </html>
        """
        msg.attach(MIMEText(body, 'html'))

        # Send email
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        server.send_message(msg)
        server.quit()

        logger.info(f"Sent verification email to {email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send verification email: {e}")
        return False


def link_messenger_account(email, messenger_type, messenger_id):
    """
    Link a messenger account to a user with the given email.
    If a user with email doesn't exist, creates a new user.

    Returns:
        The user's database ID
    """
    # Normalize email
    email = email.lower().strip()

    with db_session() as db:
        # Check if the user with this email exists
        user = UserRepository.get_by_email(db, email)

        if user:
            # Update existing user with messenger ID
            if messenger_type == "telegram":
                user.telegram_id = messenger_id
            elif messenger_type == "viber":
                user.viber_id = messenger_id
            elif messenger_type == "whatsapp":
                user.whatsapp_id = messenger_id
            else:
                raise ValueError(f"Invalid messenger type: {messenger_type}")

            db.commit()
            logger.info(f"Linked {messenger_type} account {messenger_id} to existing user {user.id}")
            return user.id
        else:
            # Create a new user with this email and messenger ID
            free_until = datetime.now() + timedelta(days=7)

            # Prepare user data
            user_data = {
                "email": email,
                "email_verified": True,
                "free_until": free_until
            }

            # Add messenger-specific ID
            user_data[f"{messenger_type}_id"] = messenger_id

            # Create user
            user = UserRepository.create_user(db, user_data)
            logger.info(f"Created new user with {messenger_type} account {messenger_id}")
            return user.id