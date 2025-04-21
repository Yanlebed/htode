# common/verification/sms_service.py

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Environment variables for SMS service configuration
SMS_SERVICE_ENABLED = os.getenv("SMS_SERVICE_ENABLED", "false").lower() == "true"
SMS_SERVICE_PROVIDER = os.getenv("SMS_SERVICE_PROVIDER", "twilio")  # Options: twilio, nexmo, test
SMS_SERVICE_DEBUG = os.getenv("SMS_SERVICE_DEBUG", "false").lower() == "true"

# Twilio credentials
TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")

# Nexmo (Vonage) credentials
NEXMO_API_KEY = os.getenv("NEXMO_API_KEY")
NEXMO_API_SECRET = os.getenv("NEXMO_API_SECRET")
NEXMO_BRAND_NAME = os.getenv("NEXMO_BRAND_NAME", "ReEstateFinder")


def send_verification_code(phone_number: str, code: str) -> bool:
    """
    Send a verification code to the specified phone number.

    Args:
        phone_number: The recipient's phone number
        code: The verification code to send

    Returns:
        True if sent successfully, False otherwise
    """
    if not SMS_SERVICE_ENABLED:
        # If SMS service is disabled, log the code for testing
        logger.info(f"SMS Service DISABLED. Would send code {code} to {phone_number}")
        return True

    # Choose the SMS provider
    if SMS_SERVICE_PROVIDER == "twilio":
        return _send_via_twilio(phone_number, code)
    elif SMS_SERVICE_PROVIDER == "nexmo":
        return _send_via_nexmo(phone_number, code)
    elif SMS_SERVICE_PROVIDER == "test":
        return _send_via_test(phone_number, code)
    else:
        logger.error(f"Unknown SMS provider: {SMS_SERVICE_PROVIDER}")
        return False


def _send_via_twilio(phone_number: str, code: str) -> bool:
    """
    Send a verification code using Twilio.

    Args:
        phone_number: The recipient's phone number
        code: The verification code to send

    Returns:
        True if sent successfully, False otherwise
    """
    try:
        from twilio.rest import Client

        # Check for required credentials
        if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
            logger.error("Missing Twilio credentials")
            return False

        # Initialize Twilio client
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

        # Prepare the message
        message_text = f"Your RealEstateFinder verification code: {code}"

        # Send the message
        message = client.messages.create(
            body=message_text,
            from_=TWILIO_PHONE_NUMBER,
            to=phone_number
        )

        logger.info(f"Sent verification code to {phone_number} via Twilio, SID: {message.sid}")
        return True

    except ImportError:
        logger.error("Twilio package not installed")
        return False
    except Exception as e:
        logger.error(f"Failed to send SMS via Twilio: {e}")
        return False


def _send_via_nexmo(phone_number: str, code: str) -> bool:
    """
    Send a verification code using Nexmo (Vonage).

    Args:
        phone_number: The recipient's phone number
        code: The verification code to send

    Returns:
        True if sent successfully, False otherwise
    """
    try:
        import vonage

        # Check for required credentials
        if not all([NEXMO_API_KEY, NEXMO_API_SECRET]):
            logger.error("Missing Nexmo credentials")
            return False

        # Initialize Nexmo client
        client = vonage.Client(key=NEXMO_API_KEY, secret=NEXMO_API_SECRET)
        sms = vonage.Sms(client)

        # Prepare the message
        message_text = f"Your RealEstateFinder verification code: {code}"

        # Send the message
        response = sms.send_message({
            'from': NEXMO_BRAND_NAME,
            'to': phone_number,
            'text': message_text
        })

        # Check the response
        if response["messages"][0]["status"] == "0":
            logger.info(f"Sent verification code to {phone_number} via Nexmo")
            return True
        else:
            error = response["messages"][0]["error-text"]
            logger.error(f"Failed to send SMS via Nexmo: {error}")
            return False

    except ImportError:
        logger.error("Vonage package not installed")
        return False
    except Exception as e:
        logger.error(f"Failed to send SMS via Nexmo: {e}")
        return False


def _send_via_test(phone_number: str, code: str) -> bool:
    """
    Test SMS provider that just logs the message.

    Args:
        phone_number: The recipient's phone number
        code: The verification code to send

    Returns:
        Always returns True
    """
    message_text = f"Your RealEstateFinder verification code: {code}"
    logger.info(f"TEST SMS: Would send to {phone_number}: {message_text}")

    # Store the code in a file if in debug mode
    if SMS_SERVICE_DEBUG:
        try:
            with open(f"sms_code_{phone_number.replace('+', '')}.txt", "w") as f:
                f.write(code)
        except Exception as e:
            logger.error(f"Failed to write debug SMS code to file: {e}")

    return True