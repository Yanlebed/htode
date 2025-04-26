# services/viber_service/app/main.py

import logging
import json
from fastapi import FastAPI, Request, Response, BackgroundTasks
from viberbot.api.viber_requests import (
    ViberMessageRequest, ViberSubscribedRequest,
    ViberUnsubscribedRequest, ViberConversationStartedRequest,
    ViberFailedRequest
)
from .bot import viber, WEBHOOK_URL, logger, state_manager
from .handlers import basic_handlers
# Import the flow integration
from .flow_integration import handle_message_with_flow

# Initialize FastAPI app
app = FastAPI(title="Viber Service API")


@app.post('/viber/webhook')
async def incoming(request: Request, background_tasks: BackgroundTasks):
    """Handle incoming Viber webhook requests"""
    # Get request body
    body = await request.body()

    # Log the request
    logger.debug("Received request: %s", body)

    try:
        # Parse the request
        viber_request = viber.parse_request(body)

        # Process different types of requests
        if isinstance(viber_request, ViberMessageRequest):
            message = viber_request.message
            user_id = viber_request.sender.id

            # Process the message asynchronously in the background with flow integration
            background_tasks.add_task(handle_message_with_flow, user_id, message)

            return Response(status_code=200)

        elif isinstance(viber_request, ViberSubscribedRequest):
            user_id = viber_request.user.id
            logger.info(f"User {user_id} subscribed")

            # Handle subscription asynchronously in the background
            background_tasks.add_task(basic_handlers.handle_subscribed, user_id)

            return Response(status_code=200)

        elif isinstance(viber_request, ViberUnsubscribedRequest):
            user_id = viber_request.user_id
            logger.info(f"User {user_id} unsubscribed")
            return Response(status_code=200)

        elif isinstance(viber_request, ViberConversationStartedRequest):
            user_id = viber_request.user.id
            logger.info(f"Conversation started with user {user_id}")

            # Handle conversation start asynchronously in the background
            background_tasks.add_task(basic_handlers.handle_conversation_started, user_id, viber_request)

            return Response(status_code=200)

        elif isinstance(viber_request, ViberFailedRequest):
            logger.error(f"Request failed: {viber_request}")
            return Response(status_code=200)

        return Response(status_code=200)
    except Exception as e:
        logger.exception(f"Error processing Viber webhook: {e}")
        return Response(status_code=200)  # Always return 200 to Viber


@app.get('/viber/set-webhook')
async def set_webhook():
    """Set the Viber webhook"""
    try:
        result = viber.set_webhook(WEBHOOK_URL)
        logger.info(f"Webhook set result: {result}")
        return {"message": "Webhook set successfully", "result": result}
    except Exception as e:
        logger.error(f"Failed to set webhook: {e}")
        return {"error": f"Failed to set webhook: {e}"}, 500


@app.get('/health')
async def health_check():
    """Simple health check endpoint"""
    return {'status': 'ok'}


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Viber service with FastAPI...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)