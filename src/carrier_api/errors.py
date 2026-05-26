"""Carrier API exception types."""

from typing import Any


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


class CarrierApiGraphqlError(CarrierApiError):
    """Raised when an authenticated Carrier GraphQL operation fails."""


class CarrierApiTokenRefreshError(CarrierApiAuthError):
    """Raised when Carrier access token refresh fails."""


# Deprecated compatibility aliases. These will be removed in a future release.
BaseError = CarrierApiError
AuthError = CarrierApiAuthError
