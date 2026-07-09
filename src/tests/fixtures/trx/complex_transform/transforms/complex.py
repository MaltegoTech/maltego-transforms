"""Complex TRX transform fixture with UI messages, exceptions, overlays."""
try:
    from maltego_trx.transform import DiscoverableTransform
except ModuleNotFoundError:
    class DiscoverableTransform:
        pass


class ComplexTransform(DiscoverableTransform):
    @classmethod
    def create_entities(cls, request, response):
        if not request.Value:
            response.addUIMessage("No value provided")
            return
        try:
            entity = response.addEntity("maltego.Person")
            entity.setValue("John Doe")
            entity.addProperty("age", "Age", "loose", "30")
            # overlay example
            entity.setOverlay("smiley", "OVERLAY-IMAGE", "CENTER")
        except Exception as e:
            response.addException(str(e))
