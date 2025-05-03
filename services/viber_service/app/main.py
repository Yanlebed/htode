# services/viber_service/app/main.py

from fastapi import FastAPI, Request, Response, BackgroundTasks
from viberbot.api.viber_requests import (
    ViberMessageRequest, ViberSubscribedRequest,
    ViberUnsubscribedRequest, ViberConversationStartedRequest,
    ViberFailedRequest
)
from .bot import viber, WEBHOOK_URL
from .handlers import basic_handlers
# Import the flow integration
from .flow_integration import handle_message_with_flow

# Import logging utilities from common modules
from common.utils.logging_config import log_context, log_operation

# Import the service logger
from .. import logger

# Initialize FastAPI app
app = FastAPI(title="Viber Service API")

logger.info("FastAPI app initialized for Viber service")


@app.post('/viber/webhook')
@log_operation("incoming_webhook")
async def incoming(request: Request, background_tasks: BackgroundTasks):
    """Handle incoming Viber webhook requests"""
    # Get request body
    body = await request.body()

    # Log the request
    logger.debug("Received webhook request", extra={
        'body_length': len(body),
        'headers': dict(request.headers)
    })

    try:
        # Parse the request
        viber_request = viber.parse_request(body)

        request_type = type(viber_request).__name__
        logger.info(f"Parsed Viber request", extra={
            'request_type': request_type
        })

        # Process different types of requests
        if isinstance(viber_request, ViberMessageRequest):
            message = viber_request.message
            user_id = viber_request.sender.id

            with log_context(logger, user_id=user_id, request_type="message"):
                logger.info(f"Processing message request", extra={
                    'user_id': user_id,
                    'message_type': type(message).__name__
                })

                # Process the message asynchronously in the background with flow integration
                background_tasks.add_task(handle_message_with_flow, user_id, message)

            return Response(status_code=200)

        elif isinstance(viber_request, ViberSubscribedRequest):
            user_id = viber_request.user.id

            with log_context(logger, user_id=user_id, request_type="subscribed"):
                logger.info(f"User subscribed", extra={'user_id': user_id})

                # Handle subscription asynchronously in the background
                background_tasks.add_task(basic_handlers.handle_subscribed, user_id)

            return Response(status_code=200)

        elif isinstance(viber_request, ViberUnsubscribedRequest):
            user_id = viber_request.user_id

            with log_context(logger, user_id=user_id, request_type="unsubscribed"):
                logger.info(f"User unsubscribed", extra={'user_id': user_id})

            return Response(status_code=200)

        elif isinstance(viber_request, ViberConversationStartedRequest):
            user_id = viber_request.user.id

            with log_context(logger, user_id=user_id, request_type="conversation_started"):
                logger.info(f"Conversation started", extra={'user_id': user_id})

                # Handle conversation start asynchronously in the background
                background_tasks.add_task(basic_handlers.handle_conversation_started, user_id, viber_request)

            return Response(status_code=200)

        elif isinstance(viber_request, ViberFailedRequest):
            logger.error(f"Viber request failed", extra={
                'request': str(viber_request),
                'request_type': 'failed'
            })
            return Response(status_code=200)

        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Error processing Viber webhook", exc_info=True, extra={
            'error_type': type(e).__name__,
            'body_length': len(body)
        })
        return Response(status_code=200)  # Always return 200 to Viber


@app.get('/viber/set-webhook')
@log_operation("set_webhook")
async def set_webhook():
    """Set the Viber webhook"""
    try:
        result = viber.set_webhook(WEBHOOK_URL)
        logger.info(f"Webhook set successfully", extra={
            'webhook_url': WEBHOOK_URL,
            'result': result
        })
        return {"message": "Webhook set successfully", "result": result}
    except Exception as e:
        logger.error(f"Failed to set webhook", exc_info=True, extra={
            'webhook_url': WEBHOOK_URL,
            'error_type': type(e).__name__
        })
        return {"error": f"Failed to set webhook: {e}"}, 500


@app.get('/health')
@log_operation("health_check")
async def health_check():
    """Simple health check endpoint"""
    logger.debug("Health check requested")
    return {'status': 'ok'}


@app.on_event("startup")
async def startup_event():
    """Log startup event"""
    logger.info("Viber service starting up", extra={
        'webhook_url': WEBHOOK_URL,
        'app_title': app.title
    })


@app.on_event("shutdown")
async def shutdown_event():
    """Log shutdown event"""
    logger.info("Viber service shutting down")


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Viber service with FastAPI...", extra={
        'host': "0.0.0.0",
        'port': 8000
    })
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)