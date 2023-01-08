class Profile:
    name: str = None
    model: str = None
    brand: str = None
    firmware: str = None
    indoor_model: str = None
    indoor_serial: str = None
    outdoor_model: str = None
    outdoor_serial: str = None
    zone_ids: [str] = None
    raw_profile_json: dict = None

    def __init__(
        self,
        system,
    ):
        self.system = system
        self.refresh()

    def refresh(self):
        self.raw_profile_json = self.system.api_connection.get_profile(system_serial=self.system.serial)
        self.model = self.raw_profile_json["model"]
        self.brand = self.raw_profile_json["brand"]
        self.firmware = self.raw_profile_json["firmware"]
        self.indoor_model = self.raw_profile_json["indoorModel"]
        self.indoor_serial = self.raw_profile_json["indoorSerial"]
        self.outdoor_model = self.raw_profile_json["outdoorModel"]
        self.outdoor_serial = self.raw_profile_json["outdoorSerial"]
        self.zone_ids = []
        for zone in self.raw_profile_json["zones"]["zone"]:
            if zone["present"] == "on":
                self.zone_ids.append(zone["$"]["id"])

    def __repr__(self):
        return {
            "model": self.model,
            "brand": self.brand,
            "firmware": self.firmware,
            "indoor_model": self.indoor_model,
            "indoor_serial": self.indoor_serial,
            "outdoor_model": self.outdoor_model,
            "outdoor_serial": self.outdoor_serial,
            "zone_ids": self.zone_ids,
        }

    def __str__(self):
        return f"{self.__repr__()}"
