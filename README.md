[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]](LICENSE)

![Project Maintenance][maintenance-shield]
[![BuyMeCoffee][buymecoffeebadge]][buymecoffee]


Api Wrapper for Carrier Infinity API using async in python, this was inspired by [this guide](https://developers.home-assistant.io/docs/api_lib_index) to be a lightweight wrapper, with simple error handling.

a lot of this is based on https://my.carrier.com/.

***

[carrier_api]: https://github.com/dahlb/carrier_api
[commits-shield]: https://img.shields.io/github/commit-activity/y/dahlb/carrier_api.svg?style=for-the-badge
[commits]: https://github.com/dahlb/carrier_api/commits/main
[forum]: https://community.home-assistant.io/
[license-shield]: https://img.shields.io/github/license/dahlb/carrier_api.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-Bren%20Dahl%20%40dahlb-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/dahlb/carrier_api.svg?style=for-the-badge
[releases]: https://github.com/dahlb/carrier_api/releases
[buymecoffee]: https://www.buymeacoffee.com/dahlb
[buymecoffeebadge]: https://img.shields.io/badge/buy%20me%20a%20coffee-donate-yellow.svg?style=for-the-badge


to update schema add this to api_connection_graphql#authed_query
```
introspection_query = get_introspection_query(**session.client.introspection_args)
execution_result = await transport.execute(parse(introspection_query))
schema = dumps(execution_result.data, indent=2)
_LOGGER.debug(schema)
with open("schema.graphql", "w") as f:
    f.write(schema)
```