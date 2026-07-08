# Copyright (c) Maltego Technologies GmbH.
from typing import List, Optional


class TransformSet:
    name: Optional[str] = None
    description: Optional[str] = None
    transforms: List[str] = []
