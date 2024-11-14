from requests import HTTPError


class BaseError(HTTPError):
    pass


class RateError(BaseError):
    pass


class AuthError(BaseError):
    pass
