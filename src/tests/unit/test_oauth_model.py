# Copyright (c) Maltego Technologies GmbH.
import os
import stat

import pytest

from maltego.model.oauth import OAuthAuthenticator

pytestmark = pytest.mark.unit


def _make_authenticator(pem_prefix: str) -> OAuthAuthenticator:
    return OAuthAuthenticator(
        name="test-oauth",
        display_name="Test OAuth",
        access_token_endpoint="https://example.com/oauth/access_token",
        access_token_input="example.token",
        app_key="key",
        app_secret="secret",
        authorization_url="https://example.com/oauth/authorize",
        icon="icon.png",
        oauth_version="2.0",
        access_token_pem_file_prefix=pem_prefix,
    )


def test_generate_keys_private_key_file_is_owner_only(tmp_path, monkeypatch):
    """The generated private key file must not be world/group readable (N11)."""
    monkeypatch.chdir(tmp_path)
    pem_prefix = str(tmp_path / "maltego_oauth_test")
    authenticator = _make_authenticator(pem_prefix)

    authenticator._generate_keys()

    prv_file_path, pub_file_path = authenticator._get_key_paths()
    assert os.path.exists(prv_file_path)
    assert os.path.exists(pub_file_path)

    prv_mode = stat.S_IMODE(os.stat(prv_file_path).st_mode)
    assert prv_mode == 0o600, f"expected private key mode 0600, got {oct(prv_mode)}"
