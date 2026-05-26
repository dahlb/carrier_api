"""Carrier API exception types."""

from typing import Any


class BaseError(Exception):
    """Base exception for Carrier API failures."""

    def __init__(self, message: object, payload: Any | None = None) -> None:
        """Initialize a Carrier API exception.

        Args:
            message: Human-readable error message or raw Carrier error payload.
            payload: Optional structured error payload from Carrier.
        """
        super().__init__(message)
        self.payload = payload


class AuthError(BaseError):
    """Raised when Carrier authentication fails or returns an unsuccessful result."""
