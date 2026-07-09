# Copyright (c) Maltego Technologies GmbH.
import inspect
import sys
import types
import typing
from typing import Any


def is_any_union_type(
        origin: Any
) -> bool:
    if not origin:
        return False

    # explicit via Union[A | ...]
    if origin is typing.Union:
        return True

    if sys.version_info >= (3, 10):
        # implicit via List[A | ...]
        return inspect.isclass(origin) and issubclass(origin, types.UnionType)  # pylint: disable=no-member

    return False
