"""Utility helpers shared by Carrier API model parsers."""

from collections.abc import Callable, Mapping
from logging import getLogger
from typing import Any

_LOGGER = getLogger(__name__)


def safely_get_json_value(
    json: Mapping[str, Any] | list[Any],
    key: str,
    callable_to_cast: Callable[[Any], Any] | None = None,
) -> Any:
    """Safely read and optionally cast a nested JSON value.

    Dot-separated key segments traverse dictionaries and lists. Missing keys,
    invalid indexes, and incompatible container types resolve to ``None`` so
    model constructors can tolerate partial Carrier payloads. Carrier sometimes
    wraps a scalar in a single-key object, either ``{"_": value}`` or one keyed
    by the field's own name, so those are unwrapped to the inner value. String
    values of ``"none"`` are normalized to ``None`` before optional casting.

    Args:
        json: Mapping or list to traverse.
        key: Dot-separated lookup path, with numeric segments allowed for lists.
        callable_to_cast: Optional callable used to convert the resolved value.

    Returns:
        The resolved and optionally cast value, or ``None`` when the path cannot
        be resolved or casting fails.
    """
    value: Any = json
    for x in key.split("."):
        if value is not None:
            try:
                value = value[x]
            except TypeError, KeyError:
                try:
                    value = value[int(x)]
                except TypeError, KeyError, ValueError, IndexError:
                    value = None

    if isinstance(value, Mapping) and len(value) == 1:
        ((wrapper_key, wrapped_value),) = value.items()
        if wrapper_key in ("_", key.rsplit(".", maxsplit=1)[-1]):
            value = wrapped_value

    try:
        if value.lower() == "none":
            value = None
    except AttributeError:
        pass

    if callable_to_cast is not None and value is not None:
        try:
            value = callable_to_cast(value)
        except TypeError, ValueError:
            _LOGGER.exception("Unable to cast JSON value")
            value = None
    return value
