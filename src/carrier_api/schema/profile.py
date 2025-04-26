from dataclasses import dataclass

from marshmallow import Schema, EXCLUDE, fields, post_load


@dataclass(kw_only=True)
class Profile:
    name: str
    serial: str
    model: str
    brand: str
    firmware: str
    indoor_model: str
    indoor_serial: str
    indoor_unit_type: str
    indoor_unit_source: str
    outdoor_model: str
    outdoor_serial: str
    outdoor_unit_type: str


class ProfileSchema(Schema):
    class Meta:
        unknown = EXCLUDE
    name = fields.String()
    serial = fields.String()
    model = fields.String()
    brand = fields.String()
    firmware = fields.String()
    indoor_model = fields.String(data_key="indoorModel")
    indoor_serial = fields.String(data_key="indoorSerial")
    indoor_unit_type = fields.String(data_key="idutype")
    indoor_unit_source = fields.String(data_key="idusource")
    outdoor_model = fields.String(data_key="outdoorModel")
    outdoor_serial = fields.String(data_key="outdoorSerial")
    outdoor_unit_type = fields.String(data_key="odutype")

    @post_load
    def make_profile(self, data, **kwargs):
        return Profile(**data)
