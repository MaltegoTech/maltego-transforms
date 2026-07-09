# Copyright (c) Maltego Technologies GmbH.
import re
from typing import get_origin, get_args
from typing import (
    Any,
    Optional,
    Dict,
    List,
    Type,
    Union
)
from enum import Enum
import logging
import warnings

# 1–128 chars, must start with a letter/digit/underscore (kills
# ".", "-", "--", ".." names), then ASCII word chars plus dot/hyphen.
_SETTING_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]{0,127}$")

from datetime import date, datetime
from dateutil.parser import parse as dateutil_parse
from dateutil.parser import ParserError

from maltego.model.types import (
    MaltegoSettingDateTypes, MaltegoSettingPrimitiveTypes, MaltegoSettingPrimitiveTypesList,
    MaltegoSettingTypes, MaltegoSettingDateTypesList,
    daterange, normalize_date, to_str_format
)
from maltego.protocol.v3.discovery.transform import V3TransformSetting, serialize_daterange

log = logging.getLogger(__name__)


def convert_transform_setting_value(
        setting_value: Optional[MaltegoSettingTypes],
        setting_type: "TransformSetting.Types"
) -> Optional[MaltegoSettingTypes]:

    if setting_value is None:
        return None

    no_json_native_types = [
        TransformSetting.Types.date,
        TransformSetting.Types.date_list,
        TransformSetting.Types.datetime,
        TransformSetting.Types.datetime_range,
    ]

    if setting_type in no_json_native_types:
        if isinstance(setting_value, list):
            return [str(val) for val in setting_value]
        return str(setting_value)

    return setting_value


def normalize_setting_values(value: MaltegoSettingTypes) -> MaltegoSettingTypes:
    if isinstance(value, datetime):
        return normalize_date(value)
    if isinstance(value, date):
        return normalize_date(value)
    return value


class TransformSetting:
    """This class is used to define transform settings and control their behavior in the Maltego client.

        :param name: Name of the setting as referenced later in the transform function
        :type name: str
        :param display_name: This name is shown by the Maltego Client to the user
        :type display_name: str
        :param type: Type of the setting. Can be any of `TransformSetting.Types`, defaults to Types.str
        :type type: Union[Types, str], optional
        :param optional: Set to False to make setting required on each transform execution, defaults to True
        :type optional: bool, optional
        :param popup: Set to True to enforce setting popup on each transform execution, defaults to False
        :type popup: bool, optional
        :param is_global: Current SDK flag for sharing one stored setting value across transforms in the same namespace, defaults to False
        :type is_global: bool, optional
        :param is_global_setting: Compatibility flag for integrations that rely on the older global-setting naming shape, defaults to False
        :type is_global_setting: bool, optional
    """
    class Types(Enum):
        """Available setting types

        :param Enum: _description_
        :type Enum: _type_
        """
        # pylint: disable=invalid-name
        str = "string"
        float = "double"
        int = "int"
        boolean = "boolean"
        date = "date"
        datetime = "datetime"
        datetime_range = "daterange"
        str_list = "string[]"
        float_list = "double[]"
        int_list = "int[]"
        boolean_list = "boolean[]"
        date_list = "date[]"

    def __init__(
        self,
        name: str,
        display_name: str,
        type: Union[Types, str] = Types.str,  # pylint: disable=redefined-builtin
        default_value: Optional[MaltegoSettingTypes] = None,
        optional: bool = True,
        auth: bool = False,
        popup: bool = False,
        is_global: bool = False,
        is_global_setting: bool = False,
        is_oauth: bool = False,
        use_raw_name: bool = False,
    ):
        if not name or not _SETTING_NAME_RE.match(name):
            raise ValueError(
                f"TransformSetting name {name!r} is invalid. "
                "Must be non-empty and contain only letters, digits, underscores, hyphens, or dots."
            )
        default_value = normalize_setting_values(default_value)
        self.name = name
        self.display_name = display_name
        self.optional = optional
        self.type: TransformSetting.Types
        if isinstance(type, str):
            self.type = self.Types(type)
        else:
            self.type = type

        if not self.type:
            raise ValueError("Invalid Transform Setting Type None")

        self.auth = auth
        self.popup = popup
        self.set_default_value(default_value)
        self.is_oauth = is_oauth
        self.is_global = is_global
        if is_global_setting:
            warnings.warn(
                "is_global_setting is deprecated and will be removed in a future release. "
                "Use is_global=True instead — it is identical in behavior.",
                DeprecationWarning,
                stacklevel=2,
            )
        self.is_global_setting = is_global_setting
        self.use_raw_name = use_raw_name

    def _coerce_daterange_setting_type_from_str_value(
            self,
            value: str,
    ) -> Optional[MaltegoSettingDateTypes]:
        try:
            return daterange.fromstring_v3(value)
        except (ParserError, TypeError, ValueError) as e:
            log.warning(f"Could not parse daterange value '{value}': {e}")
            return None

    def _coerce_datetime_setting_type_from_str_value(
            self,
            value: str,
    ) -> Optional[MaltegoSettingDateTypes]:
        try:
            return normalize_date(dateutil_parse(value))
        except ParserError:
            return None

    def _coerce_date_setting_type_from_str_value(
            self,
            value: str,
    ) -> Optional[MaltegoSettingDateTypes]:
        try:
            return normalize_date(dateutil_parse(value).date())
        except ParserError:
            return None

    def _coerce_all_date_setting_type_from_str_value(
            self,
            value: str,
    ) -> Optional[MaltegoSettingDateTypes]:
        if not isinstance(value, str):
            return None

        if self.type is TransformSetting.Types.datetime:
            return self._coerce_datetime_setting_type_from_str_value(value)

        if self.type is TransformSetting.Types.date:
            return self._coerce_date_setting_type_from_str_value(value)

        if self.type is TransformSetting.Types.datetime_range:
            return self._coerce_daterange_setting_type_from_str_value(value)

        return None

    def _coerce_primitive_setting_type_from_str_value(
        self,
        value: str,
        overwrite_type: Optional["TransformSetting.Types"] = None
    ) -> Optional[MaltegoSettingPrimitiveTypes]:
        if overwrite_type is not None:
            type_ = overwrite_type
        else:
            type_ = self.type
        if type_ is TransformSetting.Types.boolean:  # bool subclasses int so we need to check it first
            if value == "":
                return None
            return value in ("true", "True")

        try:
            if type_ is TransformSetting.Types.str:  # bool subclasses int so we need to check it first
                return str(value)

            if type_ is TransformSetting.Types.int:  # bool subclasses int so we need to check it first
                return int(value)

            if type_ is TransformSetting.Types.float:  # bool subclasses int so we need to check it first
                return float(value)
        except ValueError:
            return None
        raise ValueError(
            f"Could not infer type {type_} for value {type(value)} "
            "_coerce_primitive_setting_type_from_str_value expects str, int, float or boolean values"
        )

    def _parse_date_list(
        self,
        date_list: List[Any],
    ) -> List[date]:
        parsed_date_list: List[date] = []
        for str_date in date_list:
            if isinstance(str_date, str):
                if parsed_date := self._coerce_date_setting_type_from_str_value(str_date):
                    if isinstance(parsed_date, date):
                        parsed_date_list.append(parsed_date)
        return parsed_date_list

    def _parse_datetime_list(
        self,
        date_list: List[Any],
    ) -> List[datetime]:

        parsed_datetime_list: List[datetime] = []
        for str_date in date_list:
            if isinstance(str_date, str):
                if parsed_date := self._coerce_datetime_setting_type_from_str_value(str_date):
                    if isinstance(parsed_date, datetime):
                        parsed_datetime_list.append(parsed_date)
        return parsed_datetime_list

    def _parse_daterange_list(
        self,
        date_list: List[Any],
    ) -> MaltegoSettingDateTypesList:
        parsed_daterange_list: List[daterange] = []
        for str_date in date_list:
            if isinstance(str_date, str):
                if parsed_date := self._coerce_daterange_setting_type_from_str_value(
                    str_date
                ):
                    if isinstance(parsed_date, daterange):
                        parsed_daterange_list.append(parsed_date)
        return parsed_daterange_list

    def _parse_generic_list(
        self,
        input_list: List[Any],
        target_type: Union[Type[str], Type[bool], Type[int], Type[float]]
    ) -> MaltegoSettingPrimitiveTypesList:
        parsed_list = []
        for elem in input_list:
            try:
                elem = target_type(elem)
                assert isinstance(elem, target_type)
                parsed_list.append(elem)
            except ValueError:
                pass
        return parsed_list

    def _deserialize_setting_value(
        self,
        value: MaltegoSettingTypes,
    ) -> Optional[MaltegoSettingTypes]:
        if value is None:
            return None

        # Empty string is treated as "no value" for non-string primitive types
        # List types fall through to raise ValueError for type mismatch
        if value == "" and self.type in (
            TransformSetting.Types.boolean,
            TransformSetting.Types.int,
            TransformSetting.Types.float,
            TransformSetting.Types.date,
            TransformSetting.Types.datetime,
            TransformSetting.Types.datetime_range,
        ):
            return None

        setting_type = _TRANSFORM_SETTING_TYPES_TO_PYTHON_TYPES[self.type]
        if get_origin(setting_type) is list:
            inner_type = get_args(setting_type)[0]
            if not isinstance(value, list):
                raise ValueError(
                    f"Expected list values for tx setting {self.name} with type {self.type}"
                )

            if self.type is TransformSetting.Types.date_list:
                return self._parse_date_list(value)
            return self._parse_generic_list(value, inner_type)

        if self.type in (
            TransformSetting.Types.boolean, TransformSetting.Types.str,
            TransformSetting.Types.int, TransformSetting.Types.float
        ):
            try:
                if issubclass(setting_type, (bool, int, float, str)) and isinstance(value, (bool, int, float, str)):
                    return setting_type(value)
                return None
            except ValueError:
                return None

        if self.type in (
            TransformSetting.Types.date,
            TransformSetting.Types.datetime,
            TransformSetting.Types.datetime_range
        ) and isinstance(value, str):
            return self._coerce_all_date_setting_type_from_str_value(value)

        return None

    def set_default_value(
        self,
        default_value: Optional[MaltegoSettingTypes] = None,
    ) -> None:
        setting_type = _TRANSFORM_SETTING_TYPES_TO_PYTHON_TYPES[self.type]
        self.default_value: Optional[MaltegoSettingTypes]
        if default_value is None:
            self.default_value = None
        elif get_origin(setting_type) is list:
            list_value = []
            setting_type_inner = get_args(setting_type)[0]
            if isinstance(default_value, list):
                for value in default_value:
                    if isinstance(value, setting_type_inner):
                        list_value.append(value)
            elif isinstance(default_value, setting_type_inner):
                list_value.append(default_value)
            self.default_value = list_value
        elif isinstance(default_value, setting_type):
            self.default_value = default_value
        else:
            raise TypeError(f"Could not parse {default_value} to type {setting_type}")

    def serialize_name(self, ns: str, transform_name: str) -> str:
        """
        Serializes the setting name based on the provided namespace and transform name.

        :param ns: Namespace for the setting.
        :type ns: str
        :param transform_name: Name of the transform to include in the serialization.
        :type transform_name: str
        :return: Serialized name or the plain `name` attribute.
        :rtype: str
        """
        if self.use_raw_name:
            return self.name

        if ns:
            ns = f"{ns}."
        if self.is_global_setting or self.is_global:
            name = f"global#{ns}{self.name}"
        elif self.is_oauth:
            name = self.name  # Preserving this behavior for OAuth settings
        else:
            name = f"{ns}{transform_name}.{self.name}"
        return name

    def transform_setting_from_blueprint(
        self,
        proto_setting_value: MaltegoSettingTypes,
    ) -> Optional[MaltegoSettingTypes]:
        return self._deserialize_setting_value(proto_setting_value)

    def to_v3_transform_setting_definition(self, ns: str, transform_name: str) -> V3TransformSetting:
        setting_type = self.type.value
        value: Optional[Any]
        if isinstance(self.default_value, daterange):
            value = serialize_daterange(self.default_value)
        elif isinstance(self.default_value, (date, datetime)):
            value = to_str_format(self.default_value)
        else:
            value = self.default_value if self.default_value is not None else None
        return V3TransformSetting(
            display_name=self.display_name,
            type=setting_type,
            name=self.serialize_name(ns, transform_name),
            optional=self.optional,
            popup=self.popup,
            default_value=convert_transform_setting_value(value, self.type),
            is_global=self.is_global,
            auth=self.auth
        )


_TRANSFORM_SETTING_TYPES_TO_PYTHON_TYPES: Dict[TransformSetting.Types, Type[MaltegoSettingTypes]] = {
    TransformSetting.Types.str: str,
    TransformSetting.Types.float: float,
    TransformSetting.Types.int: int,
    TransformSetting.Types.boolean: bool,
    TransformSetting.Types.date: date,
    TransformSetting.Types.datetime: datetime,
    TransformSetting.Types.datetime_range: daterange,
    TransformSetting.Types.str_list: list[str],
    TransformSetting.Types.float_list: list[float],
    TransformSetting.Types.int_list: list[int],
    TransformSetting.Types.boolean_list: list[bool],
    TransformSetting.Types.date_list: list[date],
    # TransformSetting.Types.url: str,
    # TransformSetting.Types.color: str
}
