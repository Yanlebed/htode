# tests/test_whatsapp_service.py

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from services.whatsapp_service.app.utils.message_utils import (
    safe_send_message, safe_send_media
)


@pytest.mark.asyncio
async def test_safe_send_message_success():
    """Test that safe_send_message works correctly when API call succeeds."""
    with patch("services.whatsapp_service.app.bot.client.messages.create") as mock_create, \
            patch("asyncio.get_event_loop") as mock_loop:
        # Mock the loop and executor
        mock_loop_instance = MagicMock()
        mock_loop.return_value = mock_loop_instance
        mock_loop_instance.run_in_executor.side_effect = lambda executor, func: asyncio.create_task(
            asyncio.coroutine(lambda: func())()
        )

        # Mock successful API call
        mock_message = MagicMock()
        mock_message.sid = "test_message_sid"
        mock_create.return_value = mock_message

        result = await safe_send_message(
            user_id="1234567890",
            text="Test message"
        )

        assert result == "test_message_sid"
        mock_create.assert_called_once()
        # Verify correct formatting for WhatsApp
        args, kwargs = mock_create.call_args
        assert kwargs["to"] == "whatsapp:1234567890"
        assert kwargs["body"] == "Test message"


@pytest.mark.asyncio
async def test_safe_send_message_with_whatsapp_prefix():
    """Test that safe_send_message handles user IDs with whatsapp: prefix."""
    with patch("services.whatsapp_service.app.bot.client.messages.create") as mock_create, \
            patch("asyncio.get_event_loop") as mock_loop:
        # Mock the loop and executor
        mock_loop_instance = MagicMock()
        mock_loop.return_value = mock_loop_instance
        mock_loop_instance.run_in_executor.side_effect = lambda executor, func: asyncio.create_task(
            asyncio.coroutine(lambda: func())()
        )

        # Mock successful API call
        mock_message = MagicMock()
        mock_message.sid = "test_message_sid"
        mock_create.return_value = mock_message

        result = await safe_send_message(
            user_id="whatsapp:1234567890",
            text="Test message"
        )

        assert result == "test_message_sid"
        # Verify prefix was not duplicated
        args, kwargs = mock_create.call_args
        assert kwargs["to"] == "whatsapp:1234567890"


@pytest.mark.asyncio
async def test_safe_send_media():
    """Test that safe_send_media works correctly."""
    with patch("services.whatsapp_service.app.bot.client.messages.create") as mock_create, \
            patch("asyncio.get_event_loop") as mock_loop:
        # Mock the loop and executor
        mock_loop_instance = MagicMock()
        mock_loop.return_value = mock_loop_instance
        mock_loop_instance.run_in_executor.side_effect = lambda executor, func: asyncio.create_task(
            asyncio.coroutine(lambda: func())()
        )

        # Mock successful API call
        mock_message = MagicMock()
        mock_message.sid = "test_message_sid"
        mock_create.return_value = mock_message

        result = await safe_send_media(
            user_id="1234567890",
            media_url="https://example.com/image.jpg",
            caption="Test caption"
        )

        assert result == "test_message_sid"
        mock_create.assert_called_once()
        # Verify correct arguments
        args, kwargs = mock_create.call_args
        assert kwargs["to"] == "whatsapp:1234567890"
        assert kwargs["body"] == "Test caption"
        assert kwargs["media_url"] == ["https://example.com/image.jpg"]


# Integration tests
@pytest.mark.asyncio
async def test_whatsapp_handle_message():
    """Test the message handler."""
    from services.whatsapp_service.app.handlers.basic_handlers import handle_message

    with patch("services.whatsapp_service.app.utils.message_utils.safe_send_message",
               new_callable=AsyncMock) as mock_send, \
            patch("services.whatsapp_service.app.bot.state_manager.get_state",
                  new_callable=AsyncMock) as mock_get_state, \
            patch("services.whatsapp_service.app.bot.state_manager.update_state",
                  new_callable=AsyncMock) as mock_update_state, \
            patch("services.whatsapp_service.app.handlers.basic_handlers.get_or_create_user") as mock_get_user:
        # Mock state and user
        mock_get_state.return_value = {"state": "start"}
        mock_get_user.return_value = 1

        # Create mock response
        mock_response = MagicMock()

        await handle_message("1234567890", "/start", [], mock_response)

        # Verify user was created/retrieved
        assert mock_get_user.called
        # Verify message was sent
        assert mock_send.called or mock_response.message.called


@pytest.mark.asyncio
async def test_whatsapp_send_ad_with_extra_buttons():
    """Test the send_ad_with_extra_buttons task."""
    from services.whatsapp_service.app.tasks import send_ad_with_extra_buttons

    with patch("services.whatsapp_service.app.utils.message_utils.safe_send_media",
               new_callable=AsyncMock) as mock_send_media, \
            patch("services.whatsapp_service.app.utils.message_utils.safe_send_message",
                  new_callable=AsyncMock) as mock_send_message, \
            patch("asyncio.run") as mock_run:
        # Force asyncio.run to just call the coroutine directly
        mock_run.side_effect = lambda coro: asyncio.get_event_loop().run_until_complete(coro)

        # Call the task with test data
        send_ad_with_extra_buttons(
            user_id="1234567890",
            text="Test ad text",
            s3_image_url="https://example.com/image.jpg",
            resource_url="https://example.com/ad/123",
            ad_id=1,
            ad_external_id="test_external_id"
        )

        # Verify media was sent with instructions
        assert mock_send_media.called
        call_args = mock_send_media.call_args[1]
        assert call_args["user_id"] == "whatsapp:1234567890"
        assert "Test ad text" in call_args["caption"]
        # Check that instructions are present
        assert "Доступні дії" in call_args["caption"]
        assert "фото 1" in call_args["caption"]