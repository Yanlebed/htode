# tests/test_viber_service.py

import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from services.viber_service.app.utils.message_utils import (
    safe_send_message, safe_send_picture
)


@pytest.mark.asyncio
async def test_safe_send_message_success():
    """Test that safe_send_message works correctly when API call succeeds."""
    with patch("services.viber_service.app.bot.viber.send_messages") as mock_send, \
            patch("asyncio.get_event_loop") as mock_loop:
        # Mock the loop and executor
        mock_loop_instance = MagicMock()
        mock_loop.return_value = mock_loop_instance
        mock_loop_instance.run_in_executor.side_effect = lambda executor, func: asyncio.create_task(
            asyncio.coroutine(lambda: func())()
        )

        # Mock successful API call
        mock_send.return_value = {"status": "ok"}

        result = await safe_send_message(
            user_id="test_user_id",
            text="Test message"
        )

        assert result == {"status": "ok"}
        assert mock_send.called


@pytest.mark.asyncio
async def test_safe_send_message_retry():
    """Test that safe_send_message retries on transient errors."""
    with patch("services.viber_service.app.bot.viber.send_messages") as mock_send, \
            patch("asyncio.get_event_loop") as mock_loop:
        # Mock the loop and executor
        mock_loop_instance = MagicMock()
        mock_loop.return_value = mock_loop_instance

        # Set up side effects to simulate failure then success
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Network error")
            return {"status": "ok"}

        mock_loop_instance.run_in_executor.side_effect = lambda executor, func: asyncio.create_task(
            asyncio.coroutine(lambda: side_effect() if call_count < 2 else func())()
        )

        result = await safe_send_message(
            user_id="test_user_id",
            text="Test message",
            retry_count=2,
            retry_delay=0.1  # Low delay for tests
        )

        assert result == {"status": "ok"}
        assert call_count == 2


@pytest.mark.asyncio
async def test_safe_send_picture():
    """Test that safe_send_picture works correctly."""
    with patch("services.viber_service.app.bot.viber.send_messages") as mock_send, \
            patch("asyncio.get_event_loop") as mock_loop:
        # Mock the loop and executor
        mock_loop_instance = MagicMock()
        mock_loop.return_value = mock_loop_instance
        mock_loop_instance.run_in_executor.side_effect = lambda executor, func: asyncio.create_task(
            asyncio.coroutine(lambda: func())()
        )

        # Mock successful API call
        mock_send.return_value = {"status": "ok"}

        result = await safe_send_picture(
            user_id="test_user_id",
            image_url="https://example.com/image.jpg",
            caption="Test caption"
        )

        assert result == {"status": "ok"}
        assert mock_send.called
        # Verify correct message types were sent
        args, _ = mock_send.call_args
        messages = args[1]
        assert len(messages) == 2  # Caption message and picture message


# Integration tests
@pytest.mark.asyncio
async def test_viber_handle_conversation_started():
    """Test the conversation started handler."""
    from services.viber_service.app.handlers.basic_handlers import handle_conversation_started

    with patch("services.viber_service.app.utils.message_utils.safe_send_message", new_callable=AsyncMock) as mock_send, \
            patch("services.viber_service.app.bot.state_manager.set_state", new_callable=AsyncMock) as mock_set_state, \
            patch("services.viber_service.app.bot.state_manager.update_state",
                  new_callable=AsyncMock) as mock_update_state, \
            patch("services.viber_service.app.handlers.basic_handlers.get_or_create_user") as mock_get_user:
        # Mock user_id creation
        mock_get_user.return_value = 1

        # Create mock request
        mock_request = MagicMock()
        mock_request.user.id = "test_viber_user"

        await handle_conversation_started("test_user_id", mock_request)

        # Verify message was sent
        assert mock_send.called
        # Verify state was set
        assert mock_set_state.called
        # Verify user was created/retrieved
        assert mock_get_user.called


@pytest.mark.asyncio
async def test_viber_send_ad_with_extra_buttons():
    """Test the send_ad_with_extra_buttons task."""
    from services.viber_service.app.tasks import send_ad_with_extra_buttons

    with patch("services.viber_service.app.utils.message_utils.safe_send_picture",
               new_callable=AsyncMock) as mock_send_picture, \
            patch("services.viber_service.app.utils.message_utils.safe_send_message",
                  new_callable=AsyncMock) as mock_send_message, \
            patch("asyncio.run") as mock_run:

        # Force asyncio.run to just call the coroutine directly
        mock_run.side_effect = lambda coro: asyncio.get_event_loop().run_until_complete(coro)

        # Call the task with test data
        send_ad_with_extra_buttons(
            user_id="test_viber_user",
            text="Test ad text",
            s3_image_url="https://example.com/image.jpg",
            resource_url="https://example.com/ad/123",
            ad_id=1,
            ad_external_id="test_external_id"
        )

        # Verify picture was sent
        if s3_image_url:
            assert mock_send_picture.called
        else:
            assert mock_send_message.called