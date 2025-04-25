# common/messaging/interface.py

from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Union


class MessagingInterface(ABC):
    """
    Enhanced abstract interface for messaging platforms.
    Provides a unified API for sending messages across different platforms.
    """

    @abstractmethod
    def get_platform_name(self) -> str:
        """
        Get the name of the platform this implementation handles.

        Returns:
            Platform identifier (e.g., telegram, viber, whatsapp)
        """
        pass

    @abstractmethod
    async def send_text(
            self,
            user_id: str,
            text: str,
            keyboard: Optional[Any] = None,
            **kwargs
    ) -> Union[Any, None]:
        """
        Send a text message to a user.

        Args:
            user_id: Platform-specific user identifier
            text: Message text to send
            keyboard: Optional keyboard/buttons
            **kwargs: Additional platform-specific options

        Returns:
            Platform-specific response or None if failed
        """
        pass

    @abstractmethod
    async def send_media(
            self,
            user_id: str,
            media_url: str,
            caption: Optional[str] = None,
            keyboard: Optional[Any] = None,
            **kwargs
    ) -> Union[Any, None]:
        """
        Send a media message to a user.

        Args:
            user_id: Platform-specific user identifier
            media_url: URL of the media to send
            caption: Optional caption text
            keyboard: Optional keyboard/buttons
            **kwargs: Additional platform-specific options

        Returns:
            Platform-specific response or None if failed
        """
        pass

    @abstractmethod
    async def send_menu(
            self,
            user_id: str,
            text: str,
            options: List[Dict[str, str]],
            **kwargs
    ) -> Union[Any, None]:
        """
        Send an interactive menu to a user.

        Args:
            user_id: Platform-specific user identifier
            text: Menu title or description text
            options: List of options with 'text' and 'value' keys
            **kwargs: Additional platform-specific options

        Returns:
            Platform-specific response or None if failed
        """
        pass

    @abstractmethod
    async def format_user_id(self, user_id: str) -> str:
        """
        Format a user ID for the specific platform.

        Args:
            user_id: Raw user identifier

        Returns:
            Properly formatted user ID for the platform
        """
        pass

    @abstractmethod
    async def send_ad(
            self,
            user_id: str,
            ad_data: Dict[str, Any],
            image_url: Optional[str] = None,
            **kwargs
    ) -> Union[Any, None]:
        """
        Send a real estate ad with platform-specific formatting.

        Args:
            user_id: Platform-specific user identifier
            ad_data: Dictionary with ad information
            image_url: Optional primary image URL
            **kwargs: Additional platform-specific options

        Returns:
            Platform-specific response or None if failed
        """
        pass

    @classmethod
    @abstractmethod
    def create_keyboard(
            cls,
            options: List[Dict[str, str]],
            **kwargs
    ) -> Any:
        """
        Create a platform-specific keyboard from standardized options.

        Args:
            options: List of options with 'text' and 'value' keys
            **kwargs: Additional platform-specific parameters

        Returns:
            Platform-specific keyboard object
        """
        pass