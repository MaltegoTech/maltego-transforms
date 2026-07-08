"""TRX transform with settings fixture."""
try:
    from maltego_trx.transform import DiscoverableTransform
except ModuleNotFoundError:
    class DiscoverableTransform:
        pass


class APILookup(DiscoverableTransform):
    @classmethod
    def create_entities(cls, request, response):
        api_key = request.getTransformSetting("api_key")
        value = request.Value
        entity = response.addEntity("maltego.Phrase")
        entity.setValue(f"Result for {value}")
