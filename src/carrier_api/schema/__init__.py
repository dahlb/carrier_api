"""Schema for Blueair AWS (abs)."""

from mashumaro.config import BaseConfig
from mashumaro.mixins.dict import DataClassDictMixin


class _BaseModel(DataClassDictMixin):
    """Model shared between schema definitions."""

    class Config(BaseConfig):
        """Base configuration."""

        forbid_extra_keys = False
        serialize_by_alias = True
        debug = True

from marshmallow import Schema, fields, post_dump

class BaseSchema(Schema):
    SKIP_VALUES = {None}

    @post_dump
    def remove_skip_values(self, data, **kwargs):
        return {
            key: value for key, value in data.items()
            if value not in self.SKIP_VALUES
        }