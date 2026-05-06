from collections.abc import Callable, Mapping
from logging import getLogger
from typing import Any

_LOGGER = getLogger(__name__)


def safely_get_json_value(
    json: Mapping[str, Any] | list[Any],
    key: str,
    callable_to_cast: Callable[[Any], Any] | None = None,
) -> Any:
    value: Any = json
    for x in key.split("."):
        if value is not None:
            try:
                value = value[x]
            except TypeError, KeyError:
                try:
                    value = value[int(x)]
                except TypeError, KeyError, ValueError:
                    value = None

    try:
        if value.lower() == "none":
            value = None
    except AttributeError:
        pass

    if callable_to_cast is not None and value is not None:
        try:
            value = callable_to_cast(value)
        except ValueError as error:
            _LOGGER.exception(error)
            value = None
    return value
