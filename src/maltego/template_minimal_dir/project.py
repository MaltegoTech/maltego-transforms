from maltego.server import MaltegoServerSettings, ServerHTTPSettings, run_server

# Import your transform modules here so their @register_transform decorators run.
# Example:
# from transforms import my_transforms


if __name__ == "__main__":
    settings = MaltegoServerSettings(
        server_name="New Maltego Integration",
        ns="acme.new_maltego_integration",  # choose acme.* here
        author="Acme Corp",
        http_settings=ServerHTTPSettings(
            protocol="http",
            cors_allowed_origins=["https://app.maltego.com"]
        ),
    )

    run_server(
        settings=settings,
    )
