# Copyright (c) Maltego Technologies GmbH.
from enum import Enum
from typing import Any, Dict, Literal, Type, TypeVar, Union, Optional, List
from datetime import date, datetime, timezone
import logging
import dateutil.parser

log = logging.getLogger(__name__)

MATCHING_RULE_STRICT: Literal["strict"] = "strict"
MATCHING_RULE_LOOSE: Literal["loose"] = "loose"
MatchingRule = Literal["loose", "strict"]

ENTITY_ATTRIBUTE_NAMESPACE: str = "maltego.entity"
LINK_ATTRIBUTE_NAMESPACE: str = "maltego.link"

class AttributeNames:
    """
    Class to hold attribute names for internal properties.
    """
    composite_child = "composite.child"
    composite_link = "composite"


def normalize_date(date_or_datetime: Optional[Union[datetime, date]]) -> Union[datetime, date]:
    if isinstance(date_or_datetime, datetime):
        return date_or_datetime.astimezone(timezone.utc)
    if isinstance(date_or_datetime, date):
        return date_or_datetime
    raise ValueError(f"Invalid Date {type(date_or_datetime)}")


def to_str_format(date_or_datetime: Union[date, datetime]) -> str:
    if isinstance(date_or_datetime, datetime):
        assert date_or_datetime.tzinfo == timezone.utc
        return date_or_datetime.isoformat(timespec="milliseconds").replace('+00:00', 'Z')
    if isinstance(date_or_datetime, date):
        return date_or_datetime.isoformat()
    raise TypeError(
        f"Expected datetime or date, got {type(date_or_datetime).__name__}")


def ensure_matching_rule_from_string(rule: Optional[str]) -> Optional[MatchingRule]:
    if rule is None:
        return None
    if rule == MATCHING_RULE_LOOSE:
        return MATCHING_RULE_LOOSE
    if rule == MATCHING_RULE_STRICT:
        return MATCHING_RULE_STRICT
    raise ValueError("Unrecognized matching_rule {matching_rule}")


class Url:
    pass


class Color:
    pass


class daterange:  # pylint: disable=invalid-name
    class Ranges(Enum):
        # pylint: disable=invalid-name
        today = "Today"
        week_to_date = "Week to date"
        business_week_to_date = "Business week to date"
        month_to_date = "Month to date"
        year_to_date = "Year to date"
        yesterday = "Yesterday"
        previous_week = "Previous week"
        previous_business_week = "Previous business week"
        previous_month = "Previous month"
        previous_year = "Previous year"
        last_15_minutes = "Last 15 minutes"
        last_30_minutes = "Last 30 minutes"
        last_4_hours = "Last 4 hours"
        last_12_hours = "Last 12 hours"
        last_24_hours = "Last 24 hours"
        last_7_days = "Last 7 days"
        last_30_days = "Last 30 days"
        last_60_days = "Last 60 days"
        last_90_days = "Last 90 days"
        last_6_months = "Last 6 months"
        last_1_year = "Last 1 year"
        last_2_years = "Last 2 years"
        last_5_years = "Last 5 years"
        last_10_years = "Last 10 years"
        since_unix_epoch_time = "Since Unix Epoch Time (1970)"

    def __init__(
        self,
        *,
        start: Optional[Union[date, datetime]] = None,
        end: Optional[Union[date, datetime]] = None,
        date_range: Optional[Ranges] = None
    ):
        if date_range:
            if start or end:
                raise ValueError(
                    "Must specify both 'start' and 'end' (or 'date_range')")
        else:
            if start is None or end is None:
                raise ValueError(
                    "Must specify both 'start' and 'end' (or 'date_range')")
            if start > end:
                log.warning("Start date is later than end date!")
        self.start = normalize_date(start) if start is not None else None
        self.end = normalize_date(end) if end is not None else None
        self.range = date_range

    def __str__(self) -> str:
        if self.range:
            return self.range.value
        assert isinstance(self.start, (date, datetime))
        assert isinstance(self.end, (date, datetime))
        return (
            f'{to_str_format(self.start)}'
            '/'
            f'{to_str_format(self.end)}'
        )

    def __repr__(self) -> str:
        return self.__str__()

    @classmethod
    def fromstring_v3(cls: Type["daterange"], daterange_string: str) -> "daterange":
        if isinstance(daterange_string, cls.Ranges):
            return cls(date_range=daterange_string)
        dates = daterange_string.split("/")
        if len(dates) != 2:
            try:
                return cls(date_range=cls.Ranges(daterange_string))
            except OverflowError as exception:
                log.warning(f"Timestamp Overflow exception: {exception}")
            except OSError as exception:
                log.warning(f"Timestamp localtime() failure: {exception}")
            except ValueError as exception:
                log.warning(
                    f"strptime unable to parse date string: {exception}")
        else:
            start = dateutil.parser.parse(dates[0])
            end = dateutil.parser.parse(dates[1])
            return daterange(
                start=start,
                end=end
            )
        raise TypeError(
            "Invalid date in daterange.fromstring. Expect / separated isoformat or relative range. "
            f"Got {daterange_string}"
        )

MaltegoSettingPrimitiveTypes = Union[
    str, float, int, bool,
]

MaltegoSettingPrimitiveTypesList = Union[
    list[str], list[float], list[int], list[bool],
]

MaltegoSettingDateTypes = Union[
    date, datetime, daterange,
]
MaltegoSettingDateTypesList = Union[
    list[date], list[datetime], list[daterange],
]

MaltegoSettingTypesWithoutList = Union[
    MaltegoSettingPrimitiveTypes,
    MaltegoSettingDateTypes,
    None
]

MaltegoSettingTypes = Union[
    MaltegoSettingPrimitiveTypes,
    MaltegoSettingPrimitiveTypesList,
    MaltegoSettingDateTypes,
    MaltegoSettingDateTypesList,
    None
]


EntityPropertyTypePrimitive = Union[
    str,
    float,
    int,
    bool,
    date,
    datetime,
    daterange,
    daterange.Ranges,
    Url,
    Color,
]


EntityPropertyTypeUnion = Union[
    str,
    float,
    int,
    bool,
    date,
    datetime,
    daterange,
    daterange.Ranges,
    Url,
    Color,
    "MaltegoEntity",
    List[str],
    List[int],
    List[float],
    List[bool],
    List[date],
    List[Url],
    List[Color],
    List["MaltegoEntity"],
]

EntityPropertyType = TypeVar(
    'EntityPropertyType',
    str,
    float,
    int,
    bool,
    date,
    datetime,
    daterange,
    daterange.Ranges,
    "MaltegoEntity",
    List[str],
    List[int],
    List[float],
    List[bool],
    List[date],
    List["MaltegoEntity"],
)

EntityPropertyTypeMeta = Union[
    Type[str],
    Type[float],
    Type[int],
    Type[date],
    Type[daterange],
    Type[daterange.Ranges],
    Type[Url],
    Type[Color],
    Type["MaltegoEntity"],
    Type[List[str]],
    Type[List[int]],
    Type[List[float]],
    Type[List[bool]],
    Type[List[date]],
    Type[List[Url]],
    Type[List[Color]],
    Type[List["MaltegoEntity"]],
]

xml_types: Dict[EntityPropertyTypeMeta, str] = {
    str: "string",
    date: "date",
    datetime: "datetime",
    daterange: "daterange",
    int: "int",
    bool: "boolean",
    float: "double",
    Url: "url",
    Color: "color",
    List[int]: "int[]",
    List[str]: "string[]",
    List[bool]: "boolean[]",
    List[float]: "double[]",
    List[date]: "date[]",
    List[Url]: "url[]",
    List[Color]: "color[]",
}

LinkPropertyType = TypeVar(
    'LinkPropertyType',
    str,
    float,
    int,
    bool,
    datetime,
)


v3_property_types: Dict[Type[Any], str] = {
    str: "STRING",
    date: "DATE",
    datetime: "DATE_TIME",
    daterange: "DATE_RANGE",
    int: "INT",
    bool: "BOOLEAN",
    float: "DOUBLE",
    Url: "URL",
    Color: "COLOR"
}


class LinkStyle(Enum):
    NORMAL = 0
    DASHED = 1
    DOTTED = 2
    DASHDOT = 3


class LinkColor(Enum):

    NONE = None
    BLUE = 0
    GREEN = 1
    YELLOW = 2
    PURPLE = 3
    RED = 4

    def hex_color(self) -> str:
        color_map = {
            LinkColor.BLUE: "#0000FF",
            LinkColor.GREEN: "#00FF00",
            LinkColor.YELLOW: "#FFFF00",
            LinkColor.PURPLE: "#800080",
            LinkColor.RED: "#FF0000",
            LinkColor.NONE: "#FFFFFF",
        }
        return color_map.get(self, "#FFFFFF")


class LinkThickness(Enum):
    THICKNESS_DEFAULT = None
    THICKNESS_1 = 1
    THICKNESS_2 = 2
    THICKNESS_3 = 3
    THICKNESS_4 = 4


class ExecutionState(str, Enum):
    INITIALIZED = "INITIALIZED"
    RUNNING = "RUNNING"
    FINISHED = "FINISHED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"
    TIMED_OUT = "TIMED_OUT"
