# Copyright (c) Maltego Technologies GmbH.
"""Base model for externally-facing protocol models.

Reproduces ``APIModel`` from fastapi-restful 0.6.0 (MIT License) so protocol
aliases, serialized payloads and the OpenAPI schema stay byte-identical
without depending on that package.
"""
import re

from pydantic import BaseModel, ConfigDict

_UNDERSCORE_BEFORE_UPPER_OR_DIGIT = re.compile("([0-9A-Za-z])_(?=[0-9A-Z])")
_LEADING_UPPER = re.compile("(^_*[A-Z])")


def _snake2camel(snake: str) -> str:
    """Convert a field name to its camelCase wire alias.

    ``str.title()`` runs first, so capitals inside a word are lowercased and a
    letter after a digit is capitalized: ``transformSettings`` becomes
    ``transformsettings`` and ``maltego_v3_x`` becomes ``maltegoV3X``. These
    aliases are part of the wire contract; do not replace this with
    ``pydantic.alias_generators.to_camel``.
    """
    camel = snake.title()
    camel = _UNDERSCORE_BEFORE_UPPER_OR_DIGIT.sub(lambda m: m.group(1), camel)
    return _LEADING_UPPER.sub(lambda m: m.group(1).lower(), camel)


class APIModel(BaseModel):
    """Protocol model base.

    Serializes with camelCase aliases, accepts input by alias or by field name,
    and validates from object attributes.
    """

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        alias_generator=_snake2camel,
    )
