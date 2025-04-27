from mashumaro.types import SerializationStrategy


class BooleanSerializationStrategy(SerializationStrategy, use_annotations=True):
    def __init__(self, truthy: str, falsy: str):
        self.truthy = truthy
        self.falsy = falsy

    def serialize(self, value: bool) -> str | None:
        if value is not None:
            if value:
                return self.truthy
            else:
                return self.falsy

    def deserialize(self, value: str) -> bool | None:
        if value is not None:
            return value == self.truthy
