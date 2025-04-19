# services/viber_service/app/main.py

import logging
import json
from flask import Flask, request, Response
from viberbot.api.viber_requests import (
    ViberMessageRequest, ViberSubscribedRequest,
    ViberUnsubscribedRequest, ViberConversationStartedRequest,
    ViberFailedRequest
)
from .bot import viber, WEBHOOK_URL, logger
from .handlers import basic_handlers, menu_handlers, favorites, subscription

# Initialize Flask app
app = Flask(__name__)


@app.route('/viber/webhook', methods=['POST'])
def incoming():
    """Handle incoming Viber webhook requests"""
    # Log the request
    logger.debug("Received request: %s", request.get_data())

    # Parse the request
    viber_request = viber.parse_request(request.get_data())

    # Process different types of requests
    if isinstance(viber_request, ViberMessageRequest):
        message = viber_request.message
        user_id = viber_request.sender.id

        # Process the message
        basic_handlers.handle_message(user_id, message)
        return Response(status=200)

    elif isinstance(viber_request, ViberSubscribedRequest):
        user_id = viber_request.user.id
        logger.info(f"User {user_id} subscribed")
        basic_handlers.handle_subscribed(user_id)
        return Response(status=200)

    elif isinstance(viber_request, ViberUnsubscribedRequest):
        user_id = viber_request.user_id
        logger.info(f"User {user_id} unsubscribed")
        return Response(status=200)

    elif isinstance(viber_request, ViberConversationStartedRequest):
        user_id = viber_request.user.id
        logger.info(f"Conversation started with user {user_id}")
        basic_handlers.handle_conversation_started(user_id, viber_request)
        return Response(status=200)

    elif isinstance(viber_request, ViberFailedRequest):
        logger.error(f"Request failed: {viber_request}")
        return Response(status=200)

    return Response(status=200)


@app.route('/viber/set-webhook', methods=['GET'])
def set_webhook():
    """Set the Viber webhook"""
    try:
        result = viber.set_webhook(WEBHOOK_URL)
        logger.info(f"Webhook set result: {result}")
        return "Webhook set successfully"
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")
        return f"Failed to set webhook: {e}", 500


def main():
    """Run the Flask app for Viber webhook handling"""
    logger.info("Starting Viber service...")
    app.run(host='0.0.0.0', port=8000)


if __name__ == "__main__":
    main()