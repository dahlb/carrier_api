"""Carrier API exception types."""

from graphql import GraphQLError


class BaseError(GraphQLError):
    """Base GraphQL-compatible exception for Carrier API failures."""

    pass


class AuthError(GraphQLError):
    """Raised when Carrier authentication fails or returns an unsuccessful result."""

    pass
