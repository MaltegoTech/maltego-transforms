# Copyright (c) Maltego Technologies GmbH.
"""``FastAPI(...)`` keyword arguments read from ``API_*`` environment variables.

Reproduces the settings the server previously read through fastapi-restful's
``get_api_settings()`` so existing ``API_*`` environment overrides keep working.
"""
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class FastAPIAppSettings(BaseSettings):
    """Attribute ``xxx_yyy`` is read from environment variable ``API_XXX_YYY``."""

    model_config = SettingsConfigDict(env_prefix="api_", validate_assignment=True)

    debug: bool = False
    openapi_prefix: str = ""
    openapi_url: str = "/openapi.json"
    title: str = "FastAPI"
    version: str = "0.1.0"
    disable_docs: bool = False

    @property
    def fastapi_kwargs(self) -> dict[str, Any]:
        """Keyword arguments for ``fastapi.FastAPI``; docs and ReDoc are always disabled."""
        return {
            "debug": self.debug,
            "docs_url": None,
            "openapi_prefix": self.openapi_prefix,
            "openapi_url": None if self.disable_docs else self.openapi_url,
            "redoc_url": None,
            "title": self.title,
            "version": self.version,
        }
