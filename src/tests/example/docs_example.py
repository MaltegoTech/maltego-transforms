from maltego.server import (
    register_transform,
    MaltegoEntity, MaltegoContext, MaltegoServerSettings,
    run_server, setup
)


@register_transform
async def hello_world(entity: MaltegoEntity, context: MaltegoContext) -> MaltegoEntity:
    return MaltegoEntity["maltego.Phrase"]("Hello World")

server_settings = MaltegoServerSettings(
    server_name="Maltego Transform Server",
    api_prefix="/maltego_transforms_example",
    ns='acme',
    author="Acme"
)
setup(server_settings)
if __name__ == '__main__':
    run_server(
        host="127.0.0.1",
        port=8080,
        ssl=True,
        settings=server_settings,
        log_level="INFO",
        ssl_key_file="server.key",
        ssl_cert_file="server.crt"
    )
