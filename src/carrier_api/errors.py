"""Carrier API exception types."""

from typing import Any

from aiohttp import ClientError


class CarrierApiError(Exception):
    """Base exception for Carrier API failures."""

    def __init__(self, message: object, payload: Any | None = None) -> None:
        """Initialize a Carrier API exception.

        Args:
            message: Human-readable error message or raw Carrier error payload.
            payload: Optional structured error payload from Carrier.
        """
        super().__init__(message)
        self.payload = payload


class CarrierApiAuthError(CarrierApiError):
    """Raised when Carrier authentication fails or returns an unsuccessful result."""


class CarrierApiConnectionError(CarrierApiError, ClientError):
    """Raised when Carrier API communication fails before a valid API response."""


class CarrierApiGraphqlError(CarrierApiError):
    """Raised when an authenticated Carrier GraphQL operation fails."""


class CarrierApiTokenRefreshError(CarrierApiConnectionError):
    """Raised when Carrier access token refresh fails."""


class CarrierApiWebsocketError(CarrierApiConnectionError):
    """Raised when Carrier realtime websocket communication fails."""


# Deprecated compatibility aliases. These preserve old import names but are not
# parent classes for the new CarrierApi* hierarchy, so removing them later will
# not require changing the inheritance of the supported exception classes.
BaseError = CarrierApiError
AuthError = CarrierApiAuthError
