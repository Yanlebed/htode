# common/messaging/service.py

import os
from typing import Dict, Any, Optional, List

from .unified_interface import MessagingInterface
from common.utils.logging_config import log_operation, log_context

# Import the logger from the parent module
from . import logger


class MessagingService:
    """
    Unified messaging service for sending messages across different platforms.
    Uses a plugin architecture with platform-specific adapters.
    """

    def __init__(self):
        """Initialize the messaging service without any messengers."""
        self._messengers = {}

    @log_operation("register_messenger")
    def register_messenger(self, platform: str, messenger: MessagingInterface) -> None:
        """
        Register a messenger implementation for a specific platform.

        Args:
            platform: Platform identifier (telegram, viber, whatsapp)
            messenger: Messenger implementation for that platform
        """
        with log_context(logger, platform=platform):
            self._messengers[platform] = messenger
            logger.info(f"Registered messenger for platform", extra={'platform': platform})

    @log_operation("get_messenger")
    def get_messenger(self, platform: str) -> Optional[MessagingInterface]:
        """
        Get the messenger for a specific platform.

        Args:
            platform: Platform identifier

        Returns:
            Messenger instance or None if not registered
        """
        messenger = self._messengers.get(platform)
        logger.debug("Retrieved messenger", extra={
            'platform': platform,
            'found': bool(messenger)
        })
        return messenger

    @log_operation("get_user_platform")
    async def get_user_platform(self, user_id: int) -> tuple[Optional[str], Optional[str]]:
        """
        Determine which platform a user is on and get their platform-specific ID.

        Args:
            user_id: Database user ID

        Returns:
            Tuple of (platform_name, platform_specific_id) or (None, None)
        """
        from common.messaging.unified_platform_utils import resolve_user_id

        with log_context(logger, user_id=user_id):
            # Use the centralized resolve_user_id function
            _, platform_name, platform_id = resolve_user_id(user_id)

            logger.debug("Resolved user platform", extra={
                'user_id': user_id,
                'platform_name': platform_name,
                'platform_id': str(platform_id)[:10] if platform_id else None
            })

            return platform_name, platform_id

    @log_operation("send_notification")
    async def send_notification(
            self,
            user_id: int,
            text: str,
            image_url: Optional[str] = None,
            options: Optional[List[Dict[str, str]]] = None,
            **kwargs
    ) -> bool:
        """
        Send a notification to a user using their preferred messenger.

        Args:
            user_id: Database user ID
            text: Message text
            image_url: Optional image URL
            options: Optional list of menu options
            **kwargs: Additional platform-specific parameters

        Returns:
            True if sent successfully, False otherwise
        """
        from common.messaging.unified_platform_utils import resolve_user_id, format_user_id_for_platform

        with log_context(logger, user_id=user_id, has_image=bool(image_url), has_options=bool(options)):
            # Get platform info using resolve_user_id
            _, platform_name, platform_id = resolve_user_id(user_id)

            if not platform_name or not platform_id:
                logger.warning(f"No messaging platform found for user", extra={'user_id': user_id})
                return False

            messenger = self.get_messenger(platform_name)
            if not messenger:
                logger.error(f"No messenger implementation registered for platform", extra={'platform': platform_name})
                return False

            try:
                # Format the user ID for the specific platform
                formatted_id = format_user_id_for_platform(platform_id, platform_name)

                logger.debug("Sending notification", extra={
                    'platform': platform_name,
                    'formatted_id': formatted_id[:10],
                    'text_length': len(text),
                    'has_image': bool(image_url),
                    'has_options': bool(options)
                })

                if options:
                    # Send as a menu
                    await messenger.send_menu(formatted_id, text, options, **kwargs)
                elif image_url:
                    # Send as media with caption
                    await messenger.send_media(formatted_id, image_url, caption=text, **kwargs)
                else:
                    # Send as plain text
                    await messenger.send_text(formatted_id, text, **kwargs)

                logger.info("Notification sent successfully", extra={
                    'user_id': user_id,
                    'platform': platform_name
                })
                return True
            except Exception as e:
                logger.error(f"Error sending notification", exc_info=True, extra={
                    'user_id': user_id,
                    'platform': platform_name,
                    'error_type': type(e).__name__
                })
                return False

    @log_operation("send_ad")
    async def send_ad(
            self,
            user_id: int,
            ad_data: Dict[str, Any],
            image_url: Optional[str] = None,
            **kwargs
    ) -> bool:
        """
        Send an ad to a user using their preferred messenger.

        Args:
            user_id: Database user ID
            ad_data: Dictionary with ad information
            image_url: Optional primary image URL
            **kwargs: Additional platform-specific parameters

        Returns:
            True if sent successfully, False otherwise
        """
        from common.messaging.unified_platform_utils import resolve_user_id, format_user_id_for_platform

        with log_context(logger, user_id=user_id, ad_id=ad_data.get('id')):
            # Get platform info using resolve_user_id
            _, platform_name, platform_id = resolve_user_id(user_id)

            if not platform_name or not platform_id:
                logger.warning(f"No messaging platform found for user", extra={'user_id': user_id})
                return False

            messenger = self.get_messenger(platform_name)
            if not messenger:
                logger.error(f"No messenger implementation registered for platform", extra={'platform': platform_name})
                return False

            try:
                # Format the user ID for the specific platform
                formatted_id = format_user_id_for_platform(platform_id, platform_name)

                logger.debug("Sending ad", extra={
                    'platform': platform_name,
                    'formatted_id': formatted_id[:10],
                    'ad_id': ad_data.get('id'),
                    'has_image': bool(image_url)
                })

                # Send the ad using platform-specific formatting
                await messenger.send_ad(formatted_id, ad_data, image_url, **kwargs)

                logger.info("Ad sent successfully", extra={
                    'user_id': user_id,
                    'platform': platform_name,
                    'ad_id': ad_data.get('id')
                })
                return True
            except Exception as e:
                logger.error(f"Error sending ad", exc_info=True, extra={
                    'user_id': user_id,
                    'platform': platform_name,
                    'ad_id': ad_data.get('id'),
                    'error_type': type(e).__name__
                })
                return False

    @classmethod
    @log_operation("create_for_service")
    def create_for_service(cls, service_name: str) -> 'MessagingService':
        """
        Create a messaging service for a specific service only.

        Args:
            service_name: Name of the service ('telegram', 'viber', 'whatsapp')

        Returns:
            Configured MessagingService instance with only the specified messenger
        """
        with log_context(logger, service_name=service_name):
            service = cls()

            try:
                if service_name == "telegram":
                    try:
                        from .telegram_messaging import TelegramMessaging
                        # Don't import the bot here, let the telegram service do it
                        logger.info("Telegram messenger type imported successfully")
                    except ImportError as e:
                        logger.error(f"Failed to import telegram messaging type", exc_info=True, extra={
                            'error_type': type(e).__name__
                        })
                    except Exception as e:
                        logger.error(f"Failed to initialize telegram messaging", exc_info=True, extra={
                            'error_type': type(e).__name__
                        })

                elif service_name == "viber":
                    try:
                        from .viber_messaging import ViberMessaging
                        # Check if viber bot exists in the global namespace
                        try:
                            from services.viber_service.app.bot import viber as viber_bot
                            if viber_bot:
                                service.register_messenger("viber", ViberMessaging(viber_bot))
                                logger.info("Viber messenger registered successfully")
                            else:
                                logger.error("Viber bot is None, check VIBER_AUTH_TOKEN environment variable")
                        except ImportError:
                            # This happens when not running in viber service
                            logger.debug("Viber bot not available in this context")
                    except ImportError as e:
                        logger.error(f"Failed to import viber dependencies", exc_info=True, extra={
                            'error_type': type(e).__name__
                        })
                    except Exception as e:
                        logger.error(f"Failed to initialize viber messaging", exc_info=True, extra={
                            'error_type': type(e).__name__
                        })

                elif service_name == "whatsapp":
                    try:
                        from .whatsapp_messaging import WhatsAppMessaging
                        try:
                            from services.whatsapp_service.app.bot import client as twilio_client
                            if twilio_client:
                                service.register_messenger("whatsapp", WhatsAppMessaging(twilio_client))
                                logger.info("WhatsApp messenger registered successfully")
                            else:
                                logger.error("WhatsApp client is None, check Twilio environment variables")
                        except ImportError:
                            # This happens when not running in whatsapp service
                            logger.debug("WhatsApp client not available in this context")
                    except ImportError as e:
                        logger.error(f"Failed to import whatsapp dependencies", exc_info=True, extra={
                            'error_type': type(e).__name__
                        })
                    except Exception as e:
                        logger.error(f"Failed to initialize whatsapp messaging", exc_info=True, extra={
                            'error_type': type(e).__name__
                        })
                else:
                    logger.warning(f"Unknown service name", extra={'service_name': service_name})
            except Exception as e:
                logger.error(f"Error creating messaging service", exc_info=True, extra={
                    'service_name': service_name,
                    'error_type': type(e).__name__
                })

            return service

messaging_service = MessagingService()

# Add it to the exports
__all__ = ['MessagingService', 'messaging_service']