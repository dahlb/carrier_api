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
