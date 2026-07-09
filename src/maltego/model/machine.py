# Copyright (c) Maltego Technologies GmbH.
import re
from typing import Optional
from dataclasses import dataclass

_LINE_COMMENT_RE = re.compile(r"//.*?$", re.MULTILINE)
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_RUN_RE = re.compile(r"""run\(\s*(['"])(.*?)\1""", re.DOTALL)
_TYPE_RE = re.compile(r"""type\(\s*(['"])(.*?)\1""", re.DOTALL)

@dataclass(frozen=True)
class MachineRefs:
    transforms: set[str]
    entities: set[str]
    indeterminate: bool # Indicates if the machine has run calls that cannot be resolved

def _strip_comments(s: str) -> str:
    return _LINE_COMMENT_RE.sub("", _BLOCK_COMMENT_RE.sub("", s))

def _extract_machine_refs(code: str) -> MachineRefs:
    s = _strip_comments(code)
    transforms = {m.group(2).strip() for m in _RUN_RE.finditer(s) if m.group(2).strip()}
    entities = {m.group(2).strip() for m in _TYPE_RE.finditer(s) if m.group(2).strip()}
    raw_run_calls = len(re.findall(r"\brun\s*\(", s))
    indeterminate = raw_run_calls > len(transforms)
    return MachineRefs(transforms=transforms, entities=entities, indeterminate=indeterminate)


class MaltegoMachine:
    name: Optional[str] = None
    favorite: bool = False
    enabled: bool = True
    read_only: bool = False
    code: str
    interactive: bool = False
    composite_entities: bool = False
    input_constraints: bool = False

    _refs_cache: Optional[MachineRefs] = None

    @classmethod
    def to_property_file(cls) -> str:
        file_content = ""
        properties = {"favorite": "favorite", "enabled": "enabled", "read_only": "readOnly"}
        for property_, protocol_name in properties.items():
            value = getattr(cls, property_)
            str_value = "true" if value else "false"
            file_content += f"{protocol_name}={str_value}\n"
        return file_content

    @classmethod
    def get_refs(cls) -> MachineRefs:
        """
        Return the parsed transform/entity references for this machine.
        Parsed once and cached in _refs_cache
        """
        if cls._refs_cache is None:
            cls._refs_cache = _extract_machine_refs(cls.code)
        return cls._refs_cache
