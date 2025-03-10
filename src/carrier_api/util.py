from logging import getLogger

_LOGGER = getLogger(__name__)


def safely_get_json_value(json, key, callable_to_cast=None):
    value = json
    for x in key.split("."):
        if value is not None:
            try:
                value = value[x]
            except (TypeError, KeyError):
                try:
                    value = value[int(x)]
                except (TypeError, KeyError, ValueError):
                    value = None
    if callable_to_cast is not None and value is not None:
        try:
            value = callable_to_cast(value)
        except ValueError as error:
            _LOGGER.exception(error)
            value = None
    return value
