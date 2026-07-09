"""Simple TRX transform fixture."""
try:
    from maltego_trx.transform import DiscoverableTransform
    from maltego_trx.entities import MaltegoEntity
except ModuleNotFoundError:
    class DiscoverableTransform:
        pass

    class MaltegoEntity:
        pass


class DomainToIP(DiscoverableTransform):
    @classmethod
    def create_entities(cls, request, response):
        value = request.Value
        entity = response.addEntity("maltego.IPv4Address")
        entity.setValue(f"1.2.3.4")  # placeholder
