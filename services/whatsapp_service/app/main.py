# services/whatsapp_service/app/main.py

import logging
import json
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from .bot import sanitize_phone_number, user_states
from .handlers import basic_handlers

# Initialize Flask app
app = Flask(__name__)
logger = logging.getLogger(__name__)


@app.route('/whatsapp/webhook', methods=['POST'])
def incoming_message():
    """Handle incoming WhatsApp messages from Twilio webhook"""
    try:
        # Get WhatsApp message details from Twilio request
        from_number = request.values.get('From', '')
        to_number = request.values.get('To', '')
        body = request.values.get('Body', '')
        media_count = int(request.values.get('NumMedia', 0))

        # Log incoming message
        logger.info(f"Received message from {from_number}: {body}")

        # Clean the phone number for use as a unique user ID
        user_id = sanitize_phone_number(from_number)

        # Process media if any
        media_urls = []
        if media_count > 0:
            for i in range(media_count):
                media_url = request.values.get(f'MediaUrl{i}')
                media_urls.append(media_url)

        # Generate response
        response = MessagingResponse()

        # Process the message
        basic_handlers.handle_message(user_id, body, media_urls, response)

        return str(response)
    except Exception as e:
        logger.exception(f"Error processing WhatsApp message: {e}")
        # Always return a valid response to Twilio
        response = MessagingResponse()
        return str(response)


@app.route('/whatsapp/status', methods=['POST'])
def message_status():
    """Handle message status callbacks from Twilio"""
    message_sid = request.values.get('MessageSid', '')
    message_status = request.values.get('MessageStatus', '')

    logger.info(f"Message {message_sid} status: {message_status}")

    return Response(status=200)


@app.route('/health', methods=['GET'])
def health_check():
    """Simple health check endpoint"""
    return {'status': 'ok'}


def main():
    """Run the Flask app for WhatsApp webhook handling"""
    logger.info("Starting WhatsApp service...")
    app.run(host='0.0.0.0', port=8080)


if __name__ == "__main__":
    main()