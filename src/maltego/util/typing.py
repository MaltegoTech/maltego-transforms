# Copyright (c) Maltego Technologies GmbH.
import inspect
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

    # implicit via List[A | ...]
    return inspect.isclass(origin) and issubclass(origin, types.UnionType)
