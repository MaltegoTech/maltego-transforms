# Copyright (c) Maltego Technologies GmbH.
from maltego.protocol.v3.execution.entity import DisplayInformationField


class _DisplayInformationItem:
    DISPLAY_INFORMATION_TYPE: str

    def __init__(self, name: str, value: str, content_type: str = "text/html"):
        self.name = name
        self.value = value
        self.content_type = content_type

    def to_v3_display_information(self) -> DisplayInformationField:
        return DisplayInformationField(
            name=self.name,
            value=self.value,
            type=self.content_type
        )


class DisplayLabel(_DisplayInformationItem):
    DISPLAY_INFORMATION_TYPE = "Label"


class DisplayField(_DisplayInformationItem):
    DISPLAY_INFORMATION_TYPE = "Field"
