"""
Base Channel Interface
======================
Abstract base for all messaging channel adapters.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from .models import GatewayMessage


class BaseChannel(ABC):
    """Abstract base for all messaging channels."""

    def __init__(self, config: dict):
        self.config = config
        self._initialized = False

    @abstractmethod
    def validate_webhook(self, request) -> bool:
        """Validate incoming request authenticity."""
        pass

    @abstractmethod
    def parse_inbound(self, request) -> Optional[GatewayMessage]:
        """Parse a Flask request into a normalized GatewayMessage."""
        pass

    @abstractmethod
    def send_message(self, recipient_id: str, text: str, metadata: dict = None) -> Dict[str, Any]:
        """Send a message to a user on this channel."""
        pass

    @abstractmethod
    def format_webhook_response(self, response_text: str, inbound_msg: GatewayMessage) -> Any:
        """Format response for synchronous webhook reply (if applicable)."""
        pass

    def is_configured(self) -> bool:
        return self._initialized
