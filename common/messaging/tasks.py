# common/messaging/tasks.py

import logging
import asyncio
from typing import Dict, Any, Optional, List, Union

from common.celery_app import celery_app
from common.db.models import get_platform_ids_for_user
from .service import messaging_service

logger = logging.getLogger(__name__)


@celery_app.task(name='common.messaging.tasks.send_notification')
def send_notification(user_id: int, text: str, **kwargs):
    """
    Send a notification to a user via their preferred messaging platform.

    Args:
        user_id: Database user ID
        text: Notification text
        **kwargs: Additional parameters for the notification
    """

    async def send():
        try:
            # Use the messaging service to send the notification
            success = await messaging_service.send_notification(
                user_id=user_id,
                text=text,
                **kwargs
            )

            if not success:
                logger.error(f"Failed to send notification to user {user_id}")
                return False

            return True
        except Exception as e:
            logger.error(f"Error sending notification to user {user_id}: {e}")
            return False

    # Run the async function
    try:
        return asyncio.run(send())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in send_notification: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send())
        finally:
            loop.close()


@celery_app.task(name='common.messaging.tasks.send_ad')
def send_ad(user_id: int, ad_data: Dict[str, Any], image_url: Optional[str] = None, **kwargs):
    """
    Send an ad to a user via their preferred messaging platform.

    Args:
        user_id: Database user ID
        ad_data: Dictionary with ad data
        image_url: Optional URL for the primary ad image
        **kwargs: Additional parameters for the ad
    """

    async def send():
        try:
            # Use the messaging service to send the ad
            success = await messaging_service.send_ad(
                user_id=user_id,
                ad_data=ad_data,
                image_url=image_url,
                **kwargs
            )

            if not success:
                logger.error(f"Failed to send ad to user {user_id}")
                return False

            return True
        except Exception as e:
            logger.error(f"Error sending ad to user {user_id}: {e}")
            return False

    # Run the async function
    try:
        return asyncio.run(send())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in send_ad: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send())
        finally:
            loop.close()


@celery_app.task(name='common.messaging.tasks.send_menu')
def send_menu(user_id: int, text: str, options: List[Dict[str, str]], **kwargs):
    """
    Send a menu with options to a user via their preferred messaging platform.

    Args:
        user_id: Database user ID
        text: Menu title/description text
        options: List of option dictionaries with at least 'text' and 'value' keys
        **kwargs: Additional parameters for the menu
    """

    async def send():
        try:
            # Get the platform-specific messenger
            platform, platform_id, messenger = messaging_service.get_messenger_for_user(user_id)

            if not platform or not platform_id or not messenger:
                logger.error(f"No messaging platform found for user {user_id}")
                return False

            # Format user ID for the platform
            formatted_id = await messenger.format_user_id(platform_id)

            # Send the menu
            await messenger.send_menu(
                user_id=formatted_id,
                text=text,
                options=options,
                **kwargs
            )

            return True
        except Exception as e:
            logger.error(f"Error sending menu to user {user_id}: {e}")
            return False

    # Run the async function
    try:
        return asyncio.run(send())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in send_menu: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send())
        finally:
            loop.close()


@celery_app.task(name='common.messaging.tasks.send_cross_platform_message')
def send_cross_platform_message(user_id: int, text: str, platforms: Optional[List[str]] = None, **kwargs):
    """
    Send a message to a user across multiple platforms.

    Args:
        user_id: Database user ID
        text: Message text
        platforms: Optional list of platforms to target (e.g., ["telegram", "viber"])
                  If None, will send to all available platforms for the user
        **kwargs: Additional parameters for the message
    """

    async def send():
        try:
            # Get all platform IDs for the user
            platform_ids = get_platform_ids_for_user(user_id)

            if not platform_ids:
                logger.error(f"No platform IDs found for user {user_id}")
                return False

            # Determine which platforms to send to
            target_platforms = platforms or ["telegram", "viber", "whatsapp"]
            sent_count = 0

            # Send to each platform that the user has an ID for
            for platform in target_platforms:
                platform_id_key = f"{platform}_id"
                if platform_ids.get(platform_id_key):
                    platform_id = platform_ids[platform_id_key]

                    # Get the messenger for this platform
                    messenger = messaging_service.get_messenger(platform)
                    if not messenger:
                        logger.warning(f"No messenger available for platform {platform}")
                        continue

                    # Format the user ID
                    formatted_id = await messenger.format_user_id(str(platform_id))

                    # Send the message
                    try:
                        await messenger.send_text(
                            user_id=formatted_id,
                            text=text,
                            **kwargs
                        )
                        sent_count += 1
                    except Exception as e:
                        logger.error(f"Error sending to {platform}: {e}")

            return sent_count > 0
        except Exception as e:
            logger.error(f"Error in send_cross_platform_message for user {user_id}: {e}")
            return False

    # Run the async function
    try:
        return asyncio.run(send())
    except RuntimeError as e:
        # Handle case where there's already an event loop
        logger.warning(f"RuntimeError in send_cross_platform_message: {e}")
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(send())
        finally:
            loop.close()