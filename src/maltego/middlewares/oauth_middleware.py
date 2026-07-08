# Copyright (c) Maltego Technologies GmbH.
import base64
import json
from typing import Any, Dict, List, Union, Optional, Sequence
from authlib.jose import JsonWebEncryption
from Crypto import Random
from Crypto.Cipher import PKCS1_v1_5, AES
from Crypto.Hash import SHA1
from Crypto.PublicKey.RSA import RsaKey
from maltego.model.context import MaltegoContext
from maltego.middlewares.middlewares import TransformMiddleware
from maltego.model.exception import MaltegoException
from maltego.model.graph import MaltegoGraph
from maltego.model.transform import MaltegoTransform
from maltego.model.entity import MaltegoEntity
from maltego.model.types import MaltegoSettingTypes, ExecutionState


# Generic, uniform error for any failure while decrypting/parsing the OAuth
# secrets bundle. Every failure mode in the legacy PKCS#1 v1.5 / `$`-delimited
# path (invalid RSA padding, valid padding but non-decryptable/garbage
# content, and an unrecognized number of `$`-separated fields) MUST raise
# this exact exception with this exact message. Do not add other
# MaltegoException messages/branches to the legacy decrypt path: the RSA
# public key used here is published via OAuth discovery, so a server that
# distinguishes "bad padding" from "bad content" (e.g. via a different
# error, status code, or a decode exception bubbling up as a 500) hands an
# unauthenticated attacker a Bleichenbacher/Manger padding oracle against
# its long-term key. Collapsing every failure to one indistinguishable
# outcome closes that oracle while keeping the legacy format working for
# valid tokens.
_OAUTH_SECRET_DECRYPTION_ERROR = "Failed to decrypt OAuth secrets."


def _invalid_oauth_secrets() -> MaltegoException:
    return MaltegoException(_OAUTH_SECRET_DECRYPTION_ERROR)


def _rsa_decrypt(private_key: RsaKey, ciphertext: Union[str, bytes]) -> str:
    """
    RSA Decryption function, returns decrypted plaintext in b64 encoding

    Raises MaltegoException (never a raw decode/parse error) on any failure,
    whether caused by invalid PKCS#1 v1.5 padding or by padding that is
    valid but decrypts to non-UTF8/garbage content. Both cases must be
    handled identically so they are not distinguishable to a caller -- see
    the module-level note on `_OAUTH_SECRET_DECRYPTION_ERROR`.
    """
    dsize = SHA1.digest_size
    sentinel = Random.new().read(20 + dsize)
    try:
        raw_ciphertext = base64.b64decode(ciphertext)
        cipher = PKCS1_v1_5.new(private_key)
        decrypted = cipher.decrypt(
            raw_ciphertext,
            sentinel,
            expected_pt_len=0
        )
        plaintext = decrypted.decode('utf8')
    except Exception as exc:
        # Covers: bad base64, invalid padding (sentinel returned, which is
        # not valid utf8), and valid padding but non-utf8/garbage content.
        # All of these must produce the exact same generic error.
        raise _invalid_oauth_secrets() from exc
    return plaintext


def _aes_decrypt(key: Union[str, bytes], ciphertext: Union[str, bytes]) -> str:
    """
    Deprecated AES decryption helper for the legacy desktop OAuth token format.

    This path is kept because recent desktop client releases can still send the
    legacy encrypted token format. It will be removed in a future version after
    clients have migrated to JWE.

    Raises MaltegoException (never a raw decode/unpad/value error) on any
    failure. This matters for the padding-oracle mitigation: in the 3- and
    5-field legacy formats the AES key is first recovered via `_rsa_decrypt`, so
    reaching this step means the RSA padding was *valid*. If a garbage AES
    payload were allowed to raise a raw exception here, it would surface a
    different error than an invalid-RSA-padding failure and re-expose the exact
    signal `_OAUTH_SECRET_DECRYPTION_ERROR` is meant to hide.
    """
    def unpad(string: bytes) -> bytes:
        return string[:-ord(string[len(string) - 1:])]
    try:
        key = base64.b64decode(key)
        ciphertext = base64.b64decode(ciphertext)
        cipher = AES.new(key, AES.MODE_ECB)
        plaintext = unpad(cipher.decrypt(ciphertext)).decode('utf8')
    except Exception as exc:
        raise _invalid_oauth_secrets() from exc
    return plaintext


def _decrypt_jwe(private_key: RsaKey, token: str) -> Dict[str, str]:
    """
    Decrypt a JWE Compact Serialization token (RFC 7516).
    """
    jwe = JsonWebEncryption()
    data = jwe.deserialize_compact(token.encode(), private_key.export_key())
    return json.loads(data["payload"].decode("utf-8"))


def decrypt_secrets(private_key: RsaKey, encoded_ciphertext: str) -> Dict[str, str]:
    """
    The TDS will send back an encrypted combination of the following :
    1. Token
    2. Token Secret
    3. Refresh Token
    4. Expires In
    This function decodes the combinations and decrypts as required and returns a dictionary with the following keys
            {"token":"",
            "token_secret": "",
            "refresh_token": "",
            "expires_in": ""}
    """
    if '.' in encoded_ciphertext:
        return _decrypt_jwe(private_key, encoded_ciphertext)

    encrypted_fields = encoded_ciphertext.split("$")

    if len(encrypted_fields) == 1:
        token = _rsa_decrypt(private_key, encrypted_fields[0])
        token_fields = {
            "token": token
        }

    elif len(encrypted_fields) == 2:
        token = _rsa_decrypt(private_key, encrypted_fields[0])
        token_secret = _rsa_decrypt(private_key, encrypted_fields[1])
        token_fields = {
            "token": token,
            "token_secret": token_secret
        }

    elif len(encrypted_fields) == 3:
        aes_key = _rsa_decrypt(private_key, encrypted_fields[2])
        token = _aes_decrypt(aes_key, encrypted_fields[0])
        token_secret = _aes_decrypt(aes_key, encrypted_fields[1])
        token_fields = {
            "token": token,
            "token_secret": token_secret
        }
    elif len(encrypted_fields) == 4:
        token = _rsa_decrypt(private_key, encrypted_fields[0])
        token_secret = _rsa_decrypt(private_key, encrypted_fields[1])
        refresh_token = _rsa_decrypt(private_key, encrypted_fields[2])
        expires_in = _rsa_decrypt(private_key, encrypted_fields[3])
        token_fields = {
            "token": token,
            "token_secret": token_secret,
            "refresh_token": refresh_token,
            "expires_in": expires_in
        }
    elif len(encrypted_fields) == 5:
        aes_key = _rsa_decrypt(private_key, encrypted_fields[4])
        token = _aes_decrypt(aes_key, encrypted_fields[0])
        token_secret = _aes_decrypt(aes_key, encrypted_fields[1])
        refresh_token = _aes_decrypt(aes_key, encrypted_fields[2])
        expires_in = _aes_decrypt(aes_key, encrypted_fields[3])
        token_fields = {
            "token": token,
            "token_secret": token_secret,
            "refresh_token": refresh_token,
            "expires_in": expires_in
        }
    else:
        # Unrecognized number of `$`-delimited fields. This must raise the
        # exact same generic error as an RSA decrypt/decode failure above
        # (see `_OAUTH_SECRET_DECRYPTION_ERROR`) rather than fail open with
        # empty token fields: returning empty strings would both let a
        # malformed/attacker-controlled token silently "succeed" and act as
        # a second oracle distinguisher alongside the RSA padding oracle.
        raise _invalid_oauth_secrets()

    return token_fields


class OAuthMiddleware(TransformMiddleware):
    async def before_transform(
            self,
            transform: MaltegoTransform,
            transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]],
            properties: Dict[str, MaltegoSettingTypes],
            context: MaltegoContext,
            soft_limit: int,
            hard_limit: int
    ) -> None:
        if transform.authenticator is None:
            return  # no oauth here
        setting_name = transform.authenticator.access_token_input
        oauth_token_encrypted = properties.get(setting_name)
        if oauth_token_encrypted is None:
            raise MaltegoException(
                f"Transform {transform.name} specified an OAuth authenticator, but the associated Transform setting "
                f"'{setting_name}' was not received."
            )
        token_fields = decrypt_secrets(
            transform.authenticator.get_private_key(), str(oauth_token_encrypted)
        )
        properties[setting_name] = token_fields  # type: ignore

    async def after_transform(
            self,
            transform: MaltegoTransform,
            transform_input: Union[MaltegoEntity, List[MaltegoEntity], MaltegoGraph[Any]],
            output_entities: List[MaltegoEntity],
            context: MaltegoContext,
            state: ExecutionState,
            exceptions: Optional[Sequence[Exception]] = None,
    ) -> None:
        return await super().after_transform(transform, transform_input, output_entities, context, state, exceptions)
