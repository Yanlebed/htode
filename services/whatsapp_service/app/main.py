# services/whatsapp_service/app/main.py

from fastapi import FastAPI, Form, Response, BackgroundTasks
from twilio.twiml.messaging_response import MessagingResponse
from .bot import sanitize_phone_number
from .flow_integration import handle_message_with_flow
from common.utils.logging_config import log_context, log_operation

# Import the service logger
from . import logger

# Initialize FastAPI app
app = FastAPI(title="WhatsApp Service API")

@app.post('/whatsapp/webhook')
@log_operation("incoming_message")
async def incoming_message(
    background_tasks: BackgroundTasks,
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(...),
    NumMedia: int = Form(0)
):
    """Handle incoming WhatsApp messages from Twilio webhook"""
    with log_context(logger, from_number=From, to_number=To, message_length=len(Body), num_media=NumMedia):
        try:
            # Log incoming message
            logger.info(f"Received message from {From}", extra={
                'sender': From,
                'receiver': To,
                'body_length': len(Body),
                'media_count': NumMedia
            })

            # Clean the phone number for use as a unique user ID
            user_id = sanitize_phone_number(From)

            # Process media if any
            media_urls = []
            if NumMedia > 0:
                # In a real implementation, you'd get media URLs from Form parameters
                # For example: MediaUrl0, MediaUrl1, etc.
                pass

            # Generate response
            response = MessagingResponse()

            # Process the message with flow integration
            background_tasks.add_task(
                handle_message_with_flow,
                user_id,
                Body,
                media_urls,
                response
            )

            return Response(content=str(response), media_type="application/xml")
        except Exception as e:
            logger.exception(f"Error processing WhatsApp message: {e}")
            # Always return a valid response to Twilio
            response = MessagingResponse()
            return Response(content=str(response), media_type="application/xml")

@app.post('/whatsapp/status')
@log_operation("message_status")
async def message_status(
    MessageSid: str = Form(...),
    MessageStatus: str = Form(...)
):
    """Handle message status callbacks from Twilio"""
    with log_context(logger, message_sid=MessageSid, status=MessageStatus):
        logger.info(f"Message status update", extra={
            'message_sid': MessageSid,
            'status': MessageStatus
        })
        return Response(status_code=200)

@app.get('/health')
@log_operation("health_check")
async def health_check():
    """Simple health check endpoint"""
    return {'status': 'ok'}

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting WhatsApp service with FastAPI...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=False)