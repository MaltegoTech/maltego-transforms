# Copyright (c) Maltego Technologies GmbH.
from typing import Any
import json
import zipfile
from xml.parsers.expat import ExpatError

import pytest
import xmltodict


class ZipToJSON:

    def __init__(self, tmp_path: Any) -> None:
        out_dir = tmp_path / "mtz"
        out_dir.mkdir()
        self.test_file = out_dir / "test.mtz"
        self.result: Any = {}
        self.json = None

    def to_json(self, zip_data: Any) -> Any:
        if self.json:
            return self.json
        self.test_file.write_bytes(zip_data)
        with zipfile.ZipFile(self.test_file, "r") as zip_file:
            for file in zip_file.infolist():
                print(file.filename)
                if file.filename.startswith("Icons/"):
                    # Skip icon files: their PNG bytes are produced by Pillow
                    # and differ across Python/Pillow versions.
                    continue
                try:
                    content = xmltodict.parse(
                        zip_file.read(file.filename).decode("utf-8")
                    )  # type: ignore
                except ExpatError:
                    content = zip_file.read(file.filename).decode("utf-8")
                print(content)
                self.result[file.filename] = {
                    "compress_type": file.compress_type,
                    # "date_time": file.date_time,
                    "create_version": file.create_version,
                    "extract_version": file.extract_version,
                    "file_content": content,
                }
        self.json = json.dumps(self.result, indent=4, sort_keys=True)  # type: ignore
        return self.json


@pytest.fixture
def zip_to_json(tmp_path: Any) -> ZipToJSON:
    return ZipToJSON(tmp_path)


@pytest.fixture(scope="session")
def config_file(tmpdir_factory: Any) -> Any:
    config_file = tmpdir_factory.mktemp("config").join("config.mtz")
    return config_file


@pytest.fixture(scope="session")
def example_config_file(tmpdir_factory: Any) -> Any:
    """Dedicated config file for mock_server_example, isolated from the shared
    config_file fixture so that function-scoped fixtures (mock_server,
    mock_server_non_defaults, mock_server_custom_prefix) cannot overwrite it
    before MtzConfig.get_config() performs its first lazy disk read."""
    config_file = tmpdir_factory.mktemp("example_config").join("config.mtz")
    return config_file
