from maltego.server import _server, MaltegoTransformServer, MaltegoServerSettings, run_server, setup, MaltegoEntity

server1_settings = MaltegoServerSettings(server_name="server1", api_prefix="server1")
server2_settings = MaltegoServerSettings(server_name="server2", api_prefix="server2")

server2 = MaltegoTransformServer(server2_settings)


@_server.register_transform
async def transform1(entity: MaltegoEntity) -> None:
    pass


@server2.register_transform
async def transform2(entity: MaltegoEntity) -> None:
    pass

_server.setup(server1_settings)
server2.setup(server2_settings)
_server.concat_server(server2)

if __name__ == "__main__":
    run_server(ssl=False)
