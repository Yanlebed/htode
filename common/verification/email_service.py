# common/verification/email_service.py

import logging
import smtplib
import uuid
import os
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from common.db.database import execute_query

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

    # Delete any existing tokens for this email
    delete_sql = "DELETE FROM email_verification_tokens WHERE email = %s"
    execute_query(delete_sql, [email])

    # Insert new token
    insert_sql = """
                 INSERT INTO email_verification_tokens (email, token, expires_at)
                 VALUES (%s, %s, %s) \
                 """
    execute_query(insert_sql, [email, token, expires_at])

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

    # Get the verification record
    select_sql = """
                 SELECT id, token, expires_at, attempts
                 FROM email_verification_tokens
                 WHERE email = %s \
                 """
    record = execute_query(select_sql, [email], fetchone=True)

    if not record:
        return False, "No verification token found for this email"

    # Check if expired
    if datetime.now() > record['expires_at']:
        return False, "Verification token has expired"

    # Check attempts
    if record['attempts'] >= MAX_VERIFICATION_ATTEMPTS:
        return False, "Too many verification attempts"

    # Increment attempt counter
    update_sql = """
                 UPDATE email_verification_tokens
                 SET attempts = attempts + 1
                 WHERE id = %s \
                 """
    execute_query(update_sql, [record['id']])

    # Check token
    if record['token'] != token:
        return False, "Invalid verification token"

    # Mark email as verified
    mark_email_verified(email)

    # Delete the token
    delete_sql = "DELETE FROM email_verification_tokens WHERE id = %s"
    execute_query(delete_sql, [record['id']])

    return True, None


def mark_email_verified(email):
    """Mark an email as verified"""
    update_sql = """
                 UPDATE users
                 SET email_verified = TRUE
                 WHERE email = %s \
                 """
    execute_query(update_sql, [email])
    logger.info(f"Marked email {email} as verified")


def send_verification_email(email, token):
    """Send verification email with token"""
    if not EMAIL_SERVICE_ENABLED:
        # For development, just log the token
        logger.info(f"EMAIL SERVICE DISABLED. Would send token {token} to {email}")

        # Write to file in debug mode
        if EMAIL_SERVICE_DEBUG:
            try:
                with open(f"email_token_{email.replace('@', '_at_')}.txt", "w") as f:
                    f.write(token)
            except Exception as e:
                logger.error(f"Failed to write debug email token to file: {e}")

        return True

    try:
        # Create message
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
    If user with email doesn't exist, creates a new user.

    Returns:
        The user's database ID
    """
    # Normalize email
    email = email.lower().strip()

    # Check if user with this email exists
    select_sql = "SELECT id FROM users WHERE email = %s"
    user = execute_query(select_sql, [email], fetchone=True)

    if user:
        # Update existing user
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
        # Create new user with this email and messenger ID
        free_until = (datetime.now() + timedelta(days=7)).isoformat()

        if messenger_type == "telegram":
            insert_sql = """
                         INSERT INTO users (email, email_verified, telegram_id, free_until)
                         VALUES (%s, TRUE, %s, %s) RETURNING id \
                         """
        elif messenger_type == "viber":
            insert_sql = """
                         INSERT INTO users (email, email_verified, viber_id, free_until)
                         VALUES (%s, TRUE, %s, %s) RETURNING id \
                         """
        elif messenger_type == "whatsapp":
            insert_sql = """
                         INSERT INTO users (email, email_verified, whatsapp_id, free_until)
                         VALUES (%s, TRUE, %s, %s) RETURNING id \
                         """
        else:
            raise ValueError(f"Invalid messenger type: {messenger_type}")

        user = execute_query(insert_sql, [email, messenger_id, free_until], fetchone=True, commit=True)
        logger.info(f"Created new user with {messenger_type} account {messenger_id}")
        return user['id']