# Copyright (c) Maltego Technologies GmbH.
from typing import Optional, Tuple
import logging
import os
from Crypto.PublicKey import RSA

from maltego.protocol.v3.discovery.auth import V3OAuthServiceDefinition

log = logging.getLogger(__name__)


class OAuthAuthenticator:
    name: str
    display_name: str

    access_token_endpoint: str
    access_token_input: str
    app_key: str
    app_secret: str
    authorization_url: str
    icon: str
    oauth_version: str
    callback_port: int = 63141
    access_token_pem_file_prefix: str = "maltego_oauth"
    description: Optional[str] = None
    refresh_token_endpoint: Optional[str] = None
    request_token_endpoint: Optional[str] = None
    request_type_for_access_token: Optional[str] = None
    request_type_for_authorization_url: Optional[str] = None
    request_type_for_request_token: Optional[str] = None
    use_ssl_host: bool = True
    use_client_authorization_header: Optional[bool] = None

    allow_regenerating_keys: bool = False
    _private_key_cached: Optional[RSA.RsaKey] = None
    _public_key_cached: Optional[RSA.RsaKey] = None

    def __init__(
        self,
        name: str,
        display_name: str,
        access_token_endpoint: str,
        access_token_input: str,
        app_key: str,
        app_secret: str,
        authorization_url: str,
        icon: str,
        oauth_version: str,
        callback_port: int = 63141,
        access_token_pem_file_prefix: str = "maltego_oauth",
        description: Optional[str] = None,
        refresh_token_endpoint: Optional[str] = None,
        request_token_endpoint: Optional[str] = None,
        request_type_for_access_token: Optional[str] = None,
        request_type_for_authorization_url: Optional[str] = None,
        request_type_for_request_token: Optional[str] = None,
        use_ssl_host: bool = True,
        use_client_authorization_header: Optional[bool] = None,
    ):
        self.name = name
        self.display_name = display_name
        self.access_token_endpoint = access_token_endpoint
        self.access_token_input = access_token_input
        self.app_key = app_key
        self.app_secret = app_secret
        self.authorization_url = authorization_url
        self.icon = icon
        self.oauth_version = oauth_version
        self.callback_port = callback_port
        self.access_token_pem_file_prefix = access_token_pem_file_prefix
        self.description = description
        self.refresh_token_endpoint = refresh_token_endpoint
        self.request_token_endpoint = request_token_endpoint
        self.request_type_for_access_token = request_type_for_access_token
        self.request_type_for_authorization_url = request_type_for_authorization_url
        self.request_type_for_request_token = request_type_for_request_token
        self.use_ssl_host = use_ssl_host
        self.use_client_authorization_header = use_client_authorization_header

    def _get_key_paths(self) -> Tuple[str, str]:
        prv_file_path = f"{self.access_token_pem_file_prefix}_private.pem"
        pub_file_path = f"{self.access_token_pem_file_prefix}_public.pem"
        return prv_file_path, pub_file_path

    def _generate_keys(self) -> None:
        key: RSA.RsaKey = RSA.generate(2048)
        pv_key_string = key.export_key()
        pb_key_string = key.public_key().export_key()

        prv_file_path, pub_file_path = self._get_key_paths()

        # Create the private key file restricted to the owner (0600) from the
        # start, rather than relying on umask, since it respects the RSA
        # private key.
        prv_fd = os.open(prv_file_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(prv_fd, "w", encoding='utf-8') as prv_file:
            prv_file.write(pv_key_string.decode())

        with open(pub_file_path, "w", encoding='utf-8') as pub_file:
            pub_file.write(pb_key_string.decode())

        log.info(
            f"Generated PEM keys for OAuth to {prv_file_path} and {pub_file_path}.")

    def get_public_key(self) -> RSA.RsaKey:
        if self._public_key_cached is not None:
            return self._public_key_cached
        _, pub_file_path = self._get_key_paths()
        if not os.path.exists(pub_file_path):
            if self.allow_regenerating_keys:
                self._generate_keys()
            else:
                raise ValueError(
                    f"No public key found for OAuth! Path is {pub_file_path}.")
        with open(pub_file_path, "r", encoding='utf-8') as pub_file:
            public_key = RSA.import_key(pub_file.read())
        self._public_key_cached = public_key
        return public_key

    def generate_keys_if_needed(self) -> None:
        self.get_public_key()

    def get_private_key(self) -> RSA.RsaKey:
        if self._private_key_cached is not None:
            return self._private_key_cached
        prv_file_path, _ = self._get_key_paths()
        if not os.path.exists(prv_file_path):
            raise ValueError(
                f"No private key found for OAuth! Path is {prv_file_path}.")
        with open(f"{self.access_token_pem_file_prefix}_private.pem", "r", encoding='utf-8') as prv_file:
            private_key = RSA.import_key(prv_file.read())

        self._private_key_cached = private_key
        return private_key

    def to_v3_oauth_service(self) -> V3OAuthServiceDefinition:
        return V3OAuthServiceDefinition(
            name=self.name,
            display_name=self.display_name,
            access_token_endpoint=self.access_token_endpoint,
            access_token_input=self.access_token_input,
            access_token_public_key=self.get_public_key().export_key().decode(),
            app_key=self.app_key,
            app_secret=self.app_secret,
            authorization_url=self.authorization_url,
            call_back_port=self.callback_port,
            description=self.description,
            icon_name=self.icon,
            o_auth_version=self.oauth_version,
            request_token_endpoint=self.request_token_endpoint,
            refresh_token_endpoint=self.refresh_token_endpoint,
            request_type_for_access_token=self.request_type_for_access_token,
            request_type_for_request_token=self.request_type_for_request_token,
            use_ssl_host=self.use_ssl_host,
        )
