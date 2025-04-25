"""
Common messaging interface for all platform services.
Defines the contract that all messaging implementations must follow.
"""
from abc import ABC, abstractmethod
from typing import Optional, List, Dict, Any, Union


class MessagingInterface(ABC):
    """Abstract base class defining the contract for all messaging platforms."""

    @abstractmethod
    async def send_text(
            self,
            user_id: str,
            text: str,
            **kwargs
    ) -> Union[str, Dict[str, Any], None]:
        """
        Send a text message to a user.

        Args:
            user_id: Platform-specific user identifier
            text: The message text to send
            **kwargs: Platform-specific optional parameters

        Returns:
            Message ID or response object, or None if sending failed
        """
        pass

    @abstractmethod
    async def send_media(
            self,
            user_id: str,
            media_url: str,
            caption: Optional[str] = None,
            **kwargs
    ) -> Union[str, Dict[str, Any], None]:
        """
        Send a media message to a user.

        Args:
            user_id: Platform-specific user identifier
            media_url: URL of the media to send
            caption: Optional text caption for the media
            **kwargs: Platform-specific optional parameters

        Returns:
            Message ID or response object, or None if sending failed
        """
        pass

    @abstractmethod
    async def send_menu(
            self,
            user_id: str,
            text: str,
            options: List[Dict[str, str]],
            **kwargs
    ) -> Union[str, Dict[str, Any], None]:
        """
        Send an interactive menu to a user.

        Args:
            user_id: Platform-specific user identifier
            text: Menu title or description
            options: List of menu options as dicts with at least 'text' and 'value' keys
            **kwargs: Platform-specific optional parameters

        Returns:
            Message ID or response object, or None if sending failed
        """
        pass

    @abstractmethod
    def sanitize_user_id(self, user_id: str) -> str:
        """
        Ensure user ID is in the proper format for this platform.

        Args:
            user_id: User identifier that may need formatting

        Returns:
            Properly formatted user ID
        """
        pass

    @classmethod
    @abstractmethod
    def create_keyboard(cls, options: List[Dict[str, str]], **kwargs) -> Any:
        """
        Create a platform-specific keyboard/menu from standardized options.

        Args:
            options: List of menu options as dicts with at least 'text' and 'value' keys
            **kwargs: Platform-specific keyboard parameters

        Returns:
            A platform-specific keyboard object
        """
        pass