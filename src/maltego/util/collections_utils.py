# Copyright (c) Maltego Technologies GmbH.
from typing import Iterable, Generator, TypeVar

T = TypeVar("T")


def flatten(iterables: Iterable[Iterable[T]]) -> Generator[T, None, None]:
    return (item for iterable in iterables for item in iterable)
