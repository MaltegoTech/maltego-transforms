from typing import Any, Optional, Tuple, List
import uuid
import re


MAJOR_VERSION_REGEX_GROUP_NAME = "major"
MINOR_VERSION_REGEX_GROUP_NAME = "minor"
PATCH_VERSION_REGEX_GROUP_NAME = "patch"
PRERELEASE_VERSION_REGEX_GROUP_NAME = "prerelease"
BUILD_META_VERSION_REGEX_GROUP_NAME = "buildmetadata"
EXTRA_REGEX_GROUP_NAME = "extra"
USER_AGENT_PATTERN = re.compile(
    r"^Maltego Desktop\/(?P<" +
    MAJOR_VERSION_REGEX_GROUP_NAME + r">0|[1-9]\d*)\.(?P<" +
    MINOR_VERSION_REGEX_GROUP_NAME + r">0|[1-9]\d*)\.(?P<" +
    PATCH_VERSION_REGEX_GROUP_NAME + r">0|[1-9]\d*)(?:-(?P<" +
    PRERELEASE_VERSION_REGEX_GROUP_NAME + r">(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?(?:\+(?P<" +  # pylint: disable=line-too-long
    BUILD_META_VERSION_REGEX_GROUP_NAME + r">[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))? \((?P<" +
    EXTRA_REGEX_GROUP_NAME + r">[^)]+)\)?$"
)


def create_maltego_id() -> str:
    # Generate a new UUID
    guid: uuid.UUID = uuid.uuid4()
    # Convert the UUID to an integer and mask the lower 64 bits
    guid_int: int = int(guid.int) & ((1 << 64) - 1)
    # Define the base36 alphabet
    alphabet: str = "0123456789abcdefghijklmnopqrstuvwxyz"
    # Convert the integer to a base36 string
    base36: str = ''
    while guid_int != 0:
        guid_int, i = divmod(guid_int, len(alphabet))
        base36 = alphabet[i] + base36
    # Return the base36 string

    return base36


def __parse_group(matches: re.Match[str], groupname: str, target_type: type) -> Any:
    try:
        return target_type(matches.group(groupname))
    except ValueError:
        return None


def parse_ua(
    user_agent_string: Optional[str]
) -> Tuple[Optional[int], Optional[int], Optional[int], Optional[str], Optional[str], Optional[List[str]]]:
    matches = USER_AGENT_PATTERN.fullmatch(user_agent_string) if user_agent_string else None
    if matches is not None:
        major_version = __parse_group(matches, MAJOR_VERSION_REGEX_GROUP_NAME, int)
        minor_version = __parse_group(matches, MINOR_VERSION_REGEX_GROUP_NAME, int)
        patch_version = __parse_group(matches, PATCH_VERSION_REGEX_GROUP_NAME, int)
        prerelease = __parse_group(matches, PRERELEASE_VERSION_REGEX_GROUP_NAME, str)
        build_metadata = __parse_group(matches, BUILD_META_VERSION_REGEX_GROUP_NAME, str)
        extra_str = __parse_group(matches, EXTRA_REGEX_GROUP_NAME, str)
        extra = None
        if isinstance(extra_str, str):
            extra = [extra.strip() for extra in extra_str.split(";")]
        else:
            extra = None
        return (major_version, minor_version, patch_version, prerelease, build_metadata, extra)
    return (None, None, None, None, None, None)
