# Copyright (c) Maltego Technologies GmbH.
import os

from Crypto.PublicKey import RSA

from maltego.model.oauth import OAuthAuthenticator


EXAMPLE_CALLBACK_URL = "https://127.0.0.1:63141/callback"
EXAMPLE_OAUTH_PEM_FILE_PREFIX = "test_oauth_runtime"
EXAMPLE_OAUTH_ICON = "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAABzUlEQVQ4T5WTSyhEURjH/9cwYjEMgwlRJpJHnrHxyiMLj2ZhKSVFE7GQkqwsLNh5bEjZWCllkDyilLzyWomM3Fh4lMd4m3GP7jHndube2biL0+073/c73/l//yMQQgj++ckFgqdGkAGMwILyHkvik33FKIAVqBuRCIHj+RtJoYEKkIfL/wpAveGWCOrXr1AQ7o+WdDMCdH4UQos8HWoAPKRuVcSc+ILuBB2K4sJQaolS7q3RQH362dMXkqfPkB8ZjIiXG8QbgzFUlaUA2FUpSPJowLc1cHyP7t0bdKabMLm+C4PeH47OKt8ANgV+AgV2BzZv39GfaUSPfYseeNRagQxzqGY6GhHvP9yInjrBDwHGckPQPLNDAX1lqegtSdHooBnj5OkjmjaukRiix4HVgpjBeTg/XciONmLPVq5Mgeng1YEctC6LmBWdaEwyYqI4Fh0LhxjZPqf5Ylc1Yg1BXhAvgEQA68ol3lwS2tNMqI034OTOidThJdr6aE02bHkWbx14Edl8XZKEtYs7xZhtc4dwPLyiMtGMxYZCGme5Gg3kk96+3bDZ9zXO0+t0GLfmQBD+Ziav1Ae8B9gGbxZ1jH8zymtkPlD7nfeHL+gv3H7Uzc9uAmYAAAAASUVORK5CYII="
GITHUB_OAUTH_CLIENT_ID = os.getenv("GITHUB_OAUTH_CLIENT_ID", "example-client-id")
GITHUB_OAUTH_CLIENT_SECRET = os.getenv("GITHUB_OAUTH_CLIENT_SECRET", "example-client-secret")


OAUTH = OAuthAuthenticator(
    name="maltego-transforms Test OAuth 1.0a",
    description="This is a test",
    access_token_input="test.oauth.token",
    display_name="Log in to Test OAuth",
    access_token_pem_file_prefix=EXAMPLE_OAUTH_PEM_FILE_PREFIX,
    oauth_version="1.0a",
    app_key=os.environ.get("TEST_OAUTH_APP_KEY", ""),
    app_secret=os.environ.get("TEST_OAUTH_APP_SECRET", ""),
    request_token_endpoint='https://oauth.example.com/request_token',
    request_type_for_request_token="GET",
    authorization_url="https://oauth.example.com/authorize?oauth_token={token}"
                      f"&oauth_callback={EXAMPLE_CALLBACK_URL}"
                      f"&redirect_uri={EXAMPLE_CALLBACK_URL}",
    use_ssl_host=True,
    access_token_endpoint="https://oauth.example.com/access_token",
    request_type_for_access_token="POST",
    icon=EXAMPLE_OAUTH_ICON,
)


OAUTH_2_0 = OAuthAuthenticator(
    name="maltego-transforms GitHub OAuth Test",
    description="GitHub OAuth 2.0 example. Set GITHUB_OAUTH_CLIENT_ID and GITHUB_OAUTH_CLIENT_SECRET to try it.",
    access_token_input="github.token",
    display_name="Log in to GitHub",
    access_token_pem_file_prefix=EXAMPLE_OAUTH_PEM_FILE_PREFIX,
    oauth_version="2.0",
    app_key=GITHUB_OAUTH_CLIENT_ID,
    app_secret=GITHUB_OAUTH_CLIENT_SECRET,
    authorization_url=f"https://github.com/login/oauth/authorize?client_id={GITHUB_OAUTH_CLIENT_ID}"
                      "&scope=read:user%20user:email"
                      f"&redirect_uri={EXAMPLE_CALLBACK_URL}",
    use_ssl_host=True,
    access_token_endpoint="https://github.com/login/oauth/access_token",
    request_type_for_access_token="POST",
    request_type_for_authorization_url="GET",
    use_client_authorization_header=False,
    icon=EXAMPLE_OAUTH_ICON,
)

_TEST_OAUTH_KEY = RSA.generate(2048)
_TEST_OAUTH_PUBLIC_KEY = _TEST_OAUTH_KEY.public_key()
for _auth in (OAUTH, OAUTH_2_0):
    _auth._private_key_cached = _TEST_OAUTH_KEY
    _auth._public_key_cached = _TEST_OAUTH_PUBLIC_KEY
