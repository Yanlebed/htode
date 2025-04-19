# services/whatsapp_service/app/bot.py

import logging
import os
from twilio.rest import Client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger(__name__)

# Get Twilio credentials from environment
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")  # Format: "whatsapp:+14155238886"

# Validate credentials
if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
    logger.error("Missing required Twilio credentials in environment variables")
    raise ValueError("TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_PHONE_NUMBER are required")

# Initialize Twilio client
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# Dictionary to store user states
user_states = {}


def send_message(to_number, message_body, media_url=None):
    """
    Send a WhatsApp message using Twilio

    Args:
        to_number: Recipient's WhatsApp number in format "whatsapp:+1234567890"
        message_body: Message text
        media_url: Optional URL to an image to include

    Returns:
        The Twilio message SID if successful, None otherwise
    """
    try:
        # Ensure proper WhatsApp formatting
        if not to_number.startswith("whatsapp:"):
            to_number = f"whatsapp:{to_number}"

        message_params = {
            "from_": TWILIO_PHONE_NUMBER,
            "body": message_body,
            "to": to_number
        }

        # Add media if provided
        if media_url:
            message_params["media_url"] = [media_url]

        message = client.messages.create(**message_params)
        logger.info(f"Sent message to {to_number} with SID: {message.sid}")
        return message.sid
    except Exception as e:
        logger.error(f"Failed to send WhatsApp message: {e}")
        return None


def sanitize_phone_number(phone_number):
    """
    Sanitize phone number to standard format

    Args:
        phone_number: Phone number in any format

    Returns:
        Sanitized phone number starting with + and only containing digits
    """
    # Remove "whatsapp:" prefix if present
    if phone_number.startswith("whatsapp:"):
        phone_number = phone_number[9:]

    # Remove all non-digit characters except '+'
    clean_number = ''.join(c for c in phone_number if c.isdigit() or c == '+')

    # Ensure it starts with '+'
    if not clean_number.startswith('+'):
        clean_number = '+' + clean_number

    return clean_number