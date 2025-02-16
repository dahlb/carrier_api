from graphql import GraphQLError


class BaseError(GraphQLError):
    pass


class AuthError(GraphQLError):
    pass
