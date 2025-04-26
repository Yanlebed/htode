# services/whatsapp_service/app/main.py

import logging
from fastapi import FastAPI, Form, Response, BackgroundTasks
from twilio.twiml.messaging_response import MessagingResponse
from .bot import sanitize_phone_number  # Only import what we need
# Import the flow integration
from .flow_integration import handle_message_with_flow

# Initialize FastAPI app
app = FastAPI(title="WhatsApp Service API")
logger = logging.getLogger(__name__)

@app.post('/whatsapp/webhook')
async def incoming_message(
    background_tasks: BackgroundTasks,
    From: str = Form(...),
    To: str = Form(...),
    Body: str = Form(...),
    NumMedia: int = Form(0)
):
    """Handle incoming WhatsApp messages from Twilio webhook"""
    try:
        # Log incoming message
        logger.info(f"Received message from {From}: {Body}")

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
async def message_status(
    MessageSid: str = Form(...),
    MessageStatus: str = Form(...)
):
    """Handle message status callbacks from Twilio"""
    logger.info(f"Message {MessageSid} status: {MessageStatus}")
    return Response(status_code=200)

@app.get('/health')
async def health_check():
    """Simple health check endpoint"""
    return {'status': 'ok'}

if __name__ == "__main__":
    import uvicorn
    logger.info("Starting WhatsApp service with FastAPI...")
    uvicorn.run("app.main:app", host="0.0.0.0", port=8080, reload=False)