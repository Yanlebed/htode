# common/messaging/abstract.py

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional


class AbstractMessenger(ABC):
    """Abstract base class for messaging platforms"""

    @abstractmethod
    def send_text(self, user_id: str, text: str, **kwargs) -> Any:
        """Send a text message"""
        pass

    @abstractmethod
    def send_image(self, user_id: str, image_url: str, caption: Optional[str] = None, **kwargs) -> Any:
        """Send an image message"""
        pass

    @abstractmethod
    def send_menu(self, user_id: str, text: str, options: List[Dict[str, str]], **kwargs) -> Any:
        """Send a menu with options"""
        pass