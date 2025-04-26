import typing
from logging import getLogger
from typing import Mapping, Any

from marshmallow.fields import Boolean

_LOGGER = getLogger(__name__)


class BooleanWithSerialize(Boolean):
    def _serialize(
            self,
            value: bool,
            attr: str | None,
            data: Mapping[str, Any] | None,
            **kwargs
    ) -> str:
        """Serializes ``value`` to a basic Python datatype. Noop by default.
        Concrete :class:`Field` classes should implement this method.

        Example: ::

            class TitleCase(Field):
                def _serialize(self, value, attr, obj, **kwargs):
                    if not value:
                        return ""
                    return str(value).title()

        :param value: The value to be serialized.
        :param attr: The attribute or key on the object to be serialized.
        :param obj: The object the value was pulled from.
        :param kwargs: Field-specific keyword arguments.
        :return: The serialized value
        """
        if value is not None:
            if value:
                return list(self.truthy)[0]
            else:
                return list(self.falsy)[0]
