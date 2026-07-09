# Copyright (c) Maltego Technologies GmbH.
# pylint: disable=protected-access
import base64
import pytest
from Crypto import Random
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA
from starlette.requests import Request

from maltego.server import MaltegoGraph, MaltegoContext
from tests.conftest import Phrase, generate_jwe_oauth_token
from maltego.middlewares import oauth_middleware
from maltego.middlewares.verify_metadata_middleware import VerifyMetadataMiddleware
from maltego.model.exception import MaltegoException

PHRASE = Phrase("test")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_verify_metadata_middleware_accepts_correct_metadata():
    request_content = {
        "input": {
            "metadata": {
                "entitiesTypesStat": {
                    "maltego.Phrase": 2,
                    "maltego.Person": 1
                }
            },
            "graph": {
                "entities": [
                    {"type": "maltego.Phrase"},
                    {"type": "maltego.Phrase"},
                    {"type": "maltego.Person"},
                ]
            }
        }
    }
    scope = {"type": "http", "headers": [(b"user-agent", b"test")]}
    request = Request(scope)
    request._json = request_content
    middleware = VerifyMetadataMiddleware()
    await middleware.before_transform(
        transform=None,
        transform_input=MaltegoGraph(),
        properties=None,
        context=MaltegoContext(MaltegoGraph(), request),
        soft_limit=None,
        hard_limit=None
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_verify_metadata_middleware_raises_on_incorrect_metadata():
    request_content = {
        "input": {
            "metadata": {
                "entitiesTypesStat": {
                    "maltego.Phrase": 2,
                }
            },
            "graph": {
                "entities": [
                    {"type": "maltego.Phrase"},
                    {"type": "maltego.Phrase"},
                    {"type": "maltego.Person"},
                ]
            }
        }
    }
    scope = {"type": "http", "headers": [(b"user-agent", b"test")]}
    request = Request(scope)
    request._json = request_content
    middleware = VerifyMetadataMiddleware()

    with pytest.raises(MaltegoException):
        await middleware.before_transform(
            transform=None,
            transform_input=MaltegoGraph(),
            properties=None,
            context=MaltegoContext(MaltegoGraph(), request, v3_request=True),
            soft_limit=None,
            hard_limit=None
        )


@pytest.mark.security
def test_oauth_aes():
    key = "ABEiM0RVZneImaq7zN3u/xAhMkNUZXaHmKm6u9zd7e8="
    ciphertext = "9DggDZZudcowExdeZJTjSRvpaT+u4snGA8nEHXrDxB8eAn3RLntmOnvSWEtYkLGtnDeuOk8VMfhUSrN/4SMkIyKBesPnt4zM9OQRruP74HgQmpzuYeNjKj++A3htdZMKcJcNN6aidteZ6AV0quwkNtZchHgdZoUhbOc60ssHVCoUB+XHEW2XhEf/KwPUFk4n7cQIipxq9Q0jgpciEYfODmTui8Byj43rdQxxSTkuUBUAjAionRkJTDF8szScrF41cimHROHs8A+V91F6FR4PbZDnKOznROKth6M54OIGfth+C4kGZU5zys7lZ6D6eNarUkltCE2Do01Jd7j3ZV4Y1gPugcCMi55IdxE3nJ6vHwxlN3ATX0cYcMXsnNMR/389IyGkVhEAwquTEjA3b9rUQCFbgCMhuw9rrDWHR9EIelGIceyANib24eAf5sg0Wl4yQRYYcEh1C1j5HfmUGvUfLQS5n+MaZJNJUDmsA8+vyUy8RyRRcCGjO8lrMdUAd8kE72NdAP5xay9TUipHCbQuZQc2/dsINbyvKEty3/jTq2Y2ITOALu+HFGGPs9DAfVzZ3vCP2Dthudasa2z/krvB3HkVU0HfJ7CGxqj76LhEO8cmGgaEpQyrmj9M/ltZKt8roC6ZP5V5jfvnk7yUr1NBURCanO5h42MqP74DeG11kwpwlw03pqJ215noBXSq7CQ21lyEeB1mhSFs5zrSywdUKmStzdYBLZ14oMnlmJAXw5wAnpAeYCdUchRv108VjXSVklhqcyZgKHDGOmOF2jzN3JSQkjYOOmBoRLyPi7bbIsk33XgOShybRlI0agCoDYwKT9ZTjpKjJ+9+2Ety9d3td1FPPk+KICRnMjoZNNJzVasB2Zf0fl+pF6f7em2iXRrqSIsiS1byi6gm8Omd092G9o1M7EsMGmVR8Ru5th7WeJEpVu/c1K2Z8qYQLHfXn2OXCW6MNkJltnSC8y7YvgUHf+Qg9x8gDB83hrpjjFyfYXeag/HtPfUAy1QpHYPRcQKeejfHePybC5ussGsgcsNOHhryTkUWKP6WKmjp92Hdnmw="  # pylint: disable=line-too-long
    plaintext = "eyJhbGciOiJSUzI1NiIsImtpZCI6InN5bnRoZXRpYy10ZXN0LWtleSIsInR5cCI6IkpXVCJ9.eyJhcHBpZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMCIsImF1ZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMCIsImV4cCI6MTcwMDAwMzYwMCwiZmFtaWx5X25hbWUiOiJFeGFtcGxlIiwiZ2l2ZW5fbmFtZSI6IlN5bnRoZXRpYyIsImlhdCI6MTcwMDAwMDAwMCwiaXBhZGRyIjoiMjAzLjAuMTEzLjUiLCJpc3MiOiJodHRwczovL2xvZ2luLmV4YW1wbGUuY29tLzAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMC8iLCJuYW1lIjoiU3ludGhldGljIEV4YW1wbGUiLCJuYmYiOjE3MDAwMDAwMDAsIm9pZCI6IjAwMDAwMDAwLTAwMDAtMDAwMC0wMDAwLTAwMDAwMDAwMDAwMCIsInNjcCI6IlVzZXIuUmVhZCIsInN1YiI6InN5bnRoZXRpYy1zdWJqZWN0IiwidGlkIjoiMDAwMDAwMDAtMDAwMC0wMDAwLTAwMDAtMDAwMDAwMDAwMDAwIiwidW5pcXVlX25hbWUiOiJ1c2VyQGV4YW1wbGUuY29tIiwidXBuIjoidXNlckBleGFtcGxlLmNvbSIsInZlciI6IjEuMCJ9.synthetic-signature"  # pylint: disable=line-too-long
    decrypted_text = oauth_middleware._aes_decrypt(key=key, ciphertext=ciphertext)

    assert plaintext == decrypted_text, "Decryption failed: Decrypted text does not match original plaintext"


@pytest.mark.security
def test_decrypt_jwe():
    key = RSA.generate(2048)
    payload = {"token": "tok123", "token_secret": "sec456"}
    jwe_token = generate_jwe_oauth_token(payload, key.publickey())
    assert '.' in jwe_token

    result = oauth_middleware.decrypt_secrets(key, jwe_token)

    assert result["token"] == "tok123"
    assert result["token_secret"] == "sec456"


@pytest.mark.security
def test_decrypt_jwe_accepts_supported_library_encryption_algorithm():
    key = RSA.generate(2048)
    payload = {"token": "tok123"}
    jwe_token = generate_jwe_oauth_token(
        payload,
        key.publickey(),
        header={"alg": "RSA-OAEP-256", "enc": "A128GCM"},
    )

    result = oauth_middleware.decrypt_secrets(key, jwe_token)

    assert result["token"] == "tok123"


@pytest.mark.security
def test_decrypt_legacy_single_field_rsa():
    key = RSA.generate(2048)
    cipher = PKCS1_v1_5.new(key.publickey())
    ciphertext = base64.b64encode(cipher.encrypt(b"my-token")).decode()
    assert '.' not in ciphertext
    assert '$' not in ciphertext

    result = oauth_middleware.decrypt_secrets(key, ciphertext)

    assert result["token"] == "my-token"


@pytest.mark.security
def test_decrypt_legacy_two_field_rsa():
    """A valid multi-field legacy token still decrypts correctly (N2/N7 fix
    must not affect the happy path)."""
    key = RSA.generate(2048)
    cipher = PKCS1_v1_5.new(key.publickey())
    ciphertext = "$".join([
        base64.b64encode(cipher.encrypt(b"my-token")).decode(),
        base64.b64encode(cipher.encrypt(b"my-secret")).decode(),
    ])

    result = oauth_middleware.decrypt_secrets(key, ciphertext)

    assert result["token"] == "my-token"
    assert result["token_secret"] == "my-secret"


def _assert_is_generic_oauth_decryption_error(exc_info: pytest.ExceptionInfo) -> None:
    """Shared assertion: every "bad legacy token" input must raise the exact
    same MaltegoException type/message/code, so an attacker probing the RSA
    padding oracle (N2) or the `$`-field-count fallback (N7) cannot
    distinguish *why* decryption failed from the observable outcome."""
    exc = exc_info.value
    assert type(exc) is MaltegoException  # pylint: disable=unidiomatic-typecheck
    assert exc.message == oauth_middleware._OAUTH_SECRET_DECRYPTION_ERROR
    assert exc.code == 400


@pytest.mark.security
def test_decrypt_legacy_rsa_bad_padding_raises_generic_error():
    """N2: invalid PKCS#1 v1.5 padding must not surface as a distinct
    UnicodeDecodeError (which previously bubbled up as a 500), because that
    difference is a Bleichenbacher/Manger padding oracle against the
    server's long-term RSA key."""
    key = RSA.generate(2048)
    # Random bytes of the correct RSA modulus size are, with overwhelming
    # probability, invalid PKCS#1 v1.5 ciphertext -> decrypt() returns the
    # random sentinel, which is not valid utf-8.
    bad_ciphertext = base64.b64encode(Random.new().read(key.size_in_bytes())).decode()

    with pytest.raises(MaltegoException) as exc_info:
        oauth_middleware.decrypt_secrets(key, bad_ciphertext)

    _assert_is_generic_oauth_decryption_error(exc_info)


@pytest.mark.security
def test_decrypt_legacy_rsa_valid_padding_garbage_content_raises_same_generic_error():
    """N2: valid PKCS#1 v1.5 padding wrapping non-utf8/garbage content must
    raise the identical error as bad padding -- otherwise the two cases
    remain distinguishable and the oracle persists."""
    key = RSA.generate(2048)
    cipher = PKCS1_v1_5.new(key.publickey())
    # Valid padding, but the plaintext itself is not valid utf-8.
    garbage_ciphertext = base64.b64encode(cipher.encrypt(b"\xff\xfe\x00\x80")).decode()

    with pytest.raises(MaltegoException) as exc_info:
        oauth_middleware.decrypt_secrets(key, garbage_ciphertext)

    _assert_is_generic_oauth_decryption_error(exc_info)


@pytest.mark.security
def test_decrypt_legacy_unrecognized_field_count_raises_same_generic_error():
    """N7: an unrecognized number of `$`-delimited fields must raise the
    same generic error instead of failing open with empty token fields."""
    key = RSA.generate(2048)

    with pytest.raises(MaltegoException) as exc_info:
        oauth_middleware.decrypt_secrets(key, "a$b$c$d$e$f")

    _assert_is_generic_oauth_decryption_error(exc_info)


def _legacy_aes_token_valid_rsa_key_garbage_payload(key: RSA.RsaKey) -> str:
    """Build a 3-field legacy token whose RSA-encrypted AES-key field decrypts
    with VALID padding (so `_rsa_decrypt` succeeds and we reach `_aes_decrypt`),
    but whose AES-encrypted payload fields are garbage. This is the branch that
    would re-expose the oracle if the AES step raised a raw (non-uniform) error."""
    cipher = PKCS1_v1_5.new(key.publickey())
    aes_key_b64 = base64.b64encode(Random.new().read(16))  # valid AES-128 key
    valid_rsa_key_field = base64.b64encode(cipher.encrypt(aes_key_b64)).decode()
    # 20 bytes -> not a 16-byte block multiple -> AES-ECB decrypt raises.
    garbage_aes = base64.b64encode(b"not-16-byte-aligned!").decode()
    return f"{garbage_aes}${garbage_aes}${valid_rsa_key_field}"


@pytest.mark.security
def test_decrypt_legacy_aes_valid_rsa_key_garbage_payload_raises_same_generic_error():
    """N2: in the 3/5-field formats the AES key is recovered via RSA first, so
    reaching the AES step means RSA padding was valid. A garbage AES payload
    must still raise the identical generic error -- otherwise "RSA valid, AES
    failed" is distinguishable from "RSA padding invalid" and the oracle
    survives in the legacy AES branches."""
    key = RSA.generate(2048)

    with pytest.raises(MaltegoException) as exc_info:
        oauth_middleware.decrypt_secrets(
            key, _legacy_aes_token_valid_rsa_key_garbage_payload(key)
        )

    _assert_is_generic_oauth_decryption_error(exc_info)


@pytest.mark.security
def test_decrypt_legacy_failures_are_indistinguishable():
    """Cross-check that bad-padding, valid-padding-garbage-content, the AES
    sub-path (valid RSA key + garbage AES payload), and wrong-field-count all
    raise the exact same exception type/message/code, i.e. an attacker cannot
    tell them apart from the observable response."""
    key = RSA.generate(2048)
    cipher = PKCS1_v1_5.new(key.publickey())

    bad_padding = base64.b64encode(Random.new().read(key.size_in_bytes())).decode()
    valid_padding_garbage = base64.b64encode(cipher.encrypt(b"\xff\xfe\x00\x80")).decode()
    aes_valid_rsa_garbage_payload = _legacy_aes_token_valid_rsa_key_garbage_payload(key)
    wrong_field_count = "a$b$c$d$e$f"

    errors = []
    for bad_input in (
        bad_padding,
        valid_padding_garbage,
        aes_valid_rsa_garbage_payload,
        wrong_field_count,
    ):
        with pytest.raises(MaltegoException) as exc_info:
            oauth_middleware.decrypt_secrets(key, bad_input)
        errors.append(exc_info.value)

    messages = {e.message for e in errors}
    codes = {e.code for e in errors}
    types = {type(e) for e in errors}
    assert messages == {oauth_middleware._OAUTH_SECRET_DECRYPTION_ERROR}
    assert codes == {400}
    assert types == {MaltegoException}
