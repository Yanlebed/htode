# common/messaging/abstract.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, Union, Tuple


class AbstractMessenger(ABC):
    """
    Abstract base class defining the common interface for all messaging platforms.
    All messenger implementations must implement these methods.
    """

    @abstractmethod
    async def send_text(
        self,
        user_id: str,
        text: str,
        reply_markup: Optional[Any] = None,
        **kwargs
    ) -> Any:
        """
        Send a text message to a user.

        Args:
            user_id: Platform-specific user identifier
            text: Message text to send
            reply_markup: Optional platform-specific keyboard/buttons
            **kwargs: Additional platform-specific options

        Returns:
            Platform-specific response object or message ID
        """
        pass

    @abstractmethod
    async def send_image(
        self,
        user_id: str,
        image_url: str,
        caption: Optional[str] = None,
        reply_markup: Optional[Any] = None,
        **kwargs
    ) -> Any:
        """
        Send an image message to a user.

        Args:
            user_id: Platform-specific user identifier
            image_url: URL of the image to send
            caption: Optional text caption for the image
            reply_markup: Optional platform-specific keyboard/buttons
            **kwargs: Additional platform-specific options

        Returns:
            Platform-specific response object or message ID
        """
        pass

    @abstractmethod
    async def send_menu(
        self,
        user_id: str,
        text: str,
        options: List[Dict[str, str]],
        **kwargs
    ) -> Any:
        """
        Send a menu with interactive options to a user.

        Args:
            user_id: Platform-specific user identifier
            text: Message text to accompany the menu
            options: List of option dictionaries with at least 'text' and 'value' keys
            **kwargs: Additional platform-specific options

        Returns:
            Platform-specific response object or message ID
        """
        pass

    @abstractmethod
    async def format_user_id(self, user_id: str) -> str:
        """
        Format a user ID according to platform requirements.
        For example, adding 'whatsapp:' prefix for WhatsApp numbers.

        Args:
            user_id: Raw user identifier

        Returns:
            Formatted user identifier
        """
        pass

    @abstractmethod
    async def send_ad(
        self,
        user_id: str,
        ad_data: Dict[str, Any],
        image_url: Optional[str] = None,
        **kwargs
    ) -> Any:
        """
        Send a real estate ad with appropriate formatting for the platform.

        Args:
            user_id: Platform-specific user identifier
            ad_data: Dictionary containing the ad information
            image_url: Optional URL of the primary image to include
            **kwargs: Additional platform-specific options

        Returns:
            Platform-specific response object or message ID
        """
        pass

    @property
    @abstractmethod
    def platform_name(self) -> str:
        """
        Get the platform identifier (telegram, viber, whatsapp).

        Returns:
            String identifier for the platform
        """
        pass

    @abstractmethod
    async def get_user_info(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get information about a user if available.

        Args:
            user_id: Platform-specific user identifier

        Returns:
            Dictionary with user information or None if unavailable
        """
        pass