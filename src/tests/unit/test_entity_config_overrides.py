# Copyright (c) Maltego Technologies GmbH.
from typing import List, Optional

from packaging.version import Version
import pytest

from maltego.model.context import MaltegoClientCapabilities, MaltegoUserAgent
from maltego.model.server import (
    ENTITY_CONFIG_OVERRIDES_ENV_VAR,
    EntityConfigOverride,
    EntityConfigOverrides,
    load_entity_config_overrides_from_env,
    merge_entity_config_overrides,
    parse_entity_config_overrides_json,
)
from maltego.protocol.v3.discovery.entity import (
    V3EntityDefinition,
    V3EntityField,
    V3EntityProperties,
)
from maltego.server.capability_matrix import CapabilityNegotiator, NegotiationContext
from maltego.server.v3 import (
    _has_coalesce_display_property,
    apply_entity_config_overrides,
    build_override_lookup_index,
)

pytestmark = pytest.mark.unit


def make_entity_def(
    entity_id: str,
    allowed_root: bool = False,
    display_value: str = "$property(value)",
    fields: Optional[List[V3EntityField]] = None,
) -> V3EntityDefinition:
    """Create a V3EntityDefinition for testing."""
    return V3EntityDefinition(
        id=entity_id,
        display_name="Test Entity",
        display_name_plural="Test Entities",
        icon_resource="Phrase",
        allowed_root=allowed_root,
        properties=V3EntityProperties(
            value="value",
            value_key="value",
            display_value=display_value,
            display_key="displayValue",
            image_overlay=None,
            fields=fields or [],
        ),
    )


def make_field(
    name: str,
    default_value: Optional[str] = None,
    evaluator: Optional[str] = None,
) -> V3EntityField:
    """Create a V3EntityField for testing."""
    return V3EntityField(
        name=name,
        matching_rule="strict",
        type="string",
        display_name=name.replace("_", " ").title(),
        default_value=default_value,
        evaluator=evaluator,
    )


def _apply_overrides(entity_def, entity_type_id, client_type, config):
    """Helper to apply overrides using the new index-based API."""
    index = build_override_lookup_index(config)
    return apply_entity_config_overrides(entity_def, entity_type_id, client_type, index)


class TestApplyEntityConfigOverrides:
    """Test apply_entity_config_overrides function."""

    def test_no_config_returns_unchanged(self):
        """Entity is unchanged when no config provided."""
        entity = make_entity_def("maltego.Test", allowed_root=False)
        result = _apply_overrides(entity, "maltego.Test", "desktop", None)
        assert result.allowed_root is False

    def test_no_client_type_returns_unchanged(self):
        """Entity is unchanged when client type is None."""
        config = EntityConfigOverrides(
            rules=[
                EntityConfigOverride(
                    entities=["maltego.Test"],
                    clients=["desktop"],
                    overrides={"allowed_root": True},
                )
            ]
        )
        entity = make_entity_def("maltego.Test", allowed_root=False)
        result = _apply_overrides(entity, "maltego.Test", None, config)
        assert result.allowed_root is False

    def test_override_allowed_root_for_desktop(self):
        """Override allowed_root to True for desktop client."""
        config = EntityConfigOverrides(
            rules=[
                EntityConfigOverride(
                    entities=["maltego.Affiliation", "maltego.Test"],
                    clients=["desktop"],
                    overrides={"allowed_root": True},
                )
            ]
        )
        entity = make_entity_def("maltego.Test", allowed_root=False)
        result = _apply_overrides(entity, "maltego.Test", "desktop", config)
        assert result.allowed_root is True

    def test_override_not_applied_for_wrong_client(self):
        """Override not applied when client doesn't match."""
        config = EntityConfigOverrides(
            rules=[
                EntityConfigOverride(
                    entities=["maltego.Test"],
                    clients=["desktop"],
                    overrides={"allowed_root": True},
                )
            ]
        )
        entity = make_entity_def("maltego.Test", allowed_root=False)
        result = _apply_overrides(entity, "maltego.Test", "web", config)
        assert result.allowed_root is False

    def test_override_not_applied_for_wrong_entity(self):
        """Override not applied when entity ID doesn't match."""
        config = EntityConfigOverrides(
            rules=[
                EntityConfigOverride(
                    entities=["maltego.Other"],
                    clients=["desktop"],
                    overrides={"allowed_root": True},
                )
            ]
        )
        entity = make_entity_def("maltego.Test", allowed_root=False)
        result = _apply_overrides(entity, "maltego.Test", "desktop", config)
        assert result.allowed_root is False

    def test_multiple_rules_apply_in_order(self):
        """Multiple matching rules are applied in order."""
        config = EntityConfigOverrides(
            rules=[
                EntityConfigOverride(
                    entities=["maltego.Test"],
                    clients=["desktop"],
                    overrides={"allowed_root": True},
                ),
                EntityConfigOverride(
                    entities=["maltego.Test"],
                    clients=["desktop"],
                    overrides={"visible": False},
                ),
            ]
        )
        entity = make_entity_def("maltego.Test", allowed_root=False)
        entity.visible = True
        result = _apply_overrides(entity, "maltego.Test", "desktop", config)
        assert result.allowed_root is True
        assert result.visible is False

    def test_nested_property_override(self):
        """Override can set nested properties using dot notation."""
        config = EntityConfigOverrides(
            rules=[
                EntityConfigOverride(
                    entities=["maltego.Test"],
                    clients=["desktop"],
                    overrides={"properties.display_value": "name"},
                )
            ]
        )
        entity = make_entity_def(
            "maltego.Test",
            display_value='$coalesce($property(name), $property(alias), "Unknown")',
        )
        result = _apply_overrides(entity, "maltego.Test", "desktop", config)
        assert result.properties.display_value == "name"

    def test_field_override_default_value(self):
        """Override can set field default_value using fields.{name}.{attr} syntax."""
        config = EntityConfigOverrides(
            rules=[
                EntityConfigOverride(
                    entities=["maltego.Test"],
                    clients=["desktop"],
                    overrides={"fields.display_property.default_value": "Simple Value"},
                )
            ]
        )
        entity = make_entity_def(
            "maltego.Test",
            display_value="display_property",
            fields=[
                make_field(
                    name="display_property",
                    default_value='$coalesce($property(name), "Default")',
                    evaluator="maltego.replace",
                ),
            ],
        )
        result = _apply_overrides(entity, "maltego.Test", "desktop", config)
        # Verify the field's default_value was overridden
        field = result.properties.fields[0]
        assert field.default_value == "Simple Value"

    def test_field_override_removes_evaluator(self):
        """Override can remove evaluator from a field."""
        config = EntityConfigOverrides(
            rules=[
                EntityConfigOverride(
                    entities=["maltego.Test"],
                    clients=["desktop"],
                    overrides={"fields.display_property.evaluator": None},
                )
            ]
        )
        entity = make_entity_def(
            "maltego.Test",
            display_value="display_property",
            fields=[
                make_field(
                    name="display_property",
                    default_value='$coalesce($property(name), "Default")',
                    evaluator="maltego.replace",
                ),
            ],
        )
        result = _apply_overrides(entity, "maltego.Test", "desktop", config)
        field = result.properties.fields[0]
        assert field.evaluator is None

    def test_field_override_removes_coalesce_from_field(self):
        """Override that removes coalesce from field default_value allows entity to pass Layer 2."""
        config = EntityConfigOverrides(
            rules=[
                EntityConfigOverride(
                    entities=["maltego.Test"],
                    clients=["desktop"],
                    overrides={
                        "fields.display_property.default_value": "$property(name)"
                    },
                )
            ]
        )
        # Entity has coalesce in field with evaluator
        entity = make_entity_def(
            "maltego.Test",
            display_value="display_property",
            fields=[
                make_field(
                    name="display_property",
                    default_value='$coalesce($property(name), "Default")',
                    evaluator="maltego.replace",
                ),
            ],
        )
        assert _has_coalesce_display_property(entity) is True

        # After override, coalesce is removed from field
        result = _apply_overrides(entity, "maltego.Test", "desktop", config)
        assert _has_coalesce_display_property(result) is False

    def test_field_override_nonexistent_field(self):
        """Override for nonexistent field is logged but doesn't fail."""
        config = EntityConfigOverrides(
            rules=[
                EntityConfigOverride(
                    entities=["maltego.Test"],
                    clients=["desktop"],
                    overrides={"fields.nonexistent.default_value": "value"},
                )
            ]
        )
        entity = make_entity_def("maltego.Test")
        # Should not raise, just log warning
        result = _apply_overrides(entity, "maltego.Test", "desktop", config)
        assert result is not None

    def test_field_override_invalid_syntax(self):
        """Invalid field override syntax is logged but doesn't fail."""
        config = EntityConfigOverrides(
            rules=[
                EntityConfigOverride(
                    entities=["maltego.Test"],
                    clients=["desktop"],
                    overrides={"fields.only_field_name": "value"},  # Missing attr
                )
            ]
        )
        entity = make_entity_def("maltego.Test")
        # Should not raise, just log warning
        result = _apply_overrides(entity, "maltego.Test", "desktop", config)
        assert result is not None


class TestHasCoalesceDisplayProperty:
    """Test _has_coalesce_display_property function."""

    def test_no_coalesce(self):
        """Entity without coalesce returns False."""
        entity = make_entity_def("maltego.Test", display_value="$property(value)")
        assert _has_coalesce_display_property(entity) is False

    def test_coalesce_in_display_value_not_detected(self):
        """Coalesce in display_value is NOT detected (not a supported pattern)."""
        # Note: Coalesce in display_property config is not supported.
        # Only MEF with value + evaluator pattern is supported.
        entity = make_entity_def(
            "maltego.Test",
            display_value='$coalesce($property(name), $property(alias), "Unknown")',
        )
        assert _has_coalesce_display_property(entity) is False

    def test_has_coalesce_in_field_with_evaluator(self):
        """Entity with coalesce in field default_value with evaluator returns True."""
        entity = make_entity_def(
            "maltego.Test",
            display_value="display_property",
            fields=[
                make_field(
                    name="display_property",
                    default_value='$coalesce($property(name), $property(alias), "Default")',
                    evaluator="maltego.replace",
                ),
                make_field(name="name", default_value="Test Name"),
                make_field(name="alias", default_value="Test Alias"),
            ],
        )
        assert _has_coalesce_display_property(entity) is True

    def test_field_with_evaluator_but_no_coalesce(self):
        """Entity with evaluator but no coalesce in default_value returns False."""
        entity = make_entity_def(
            "maltego.Test",
            display_value="display_property",
            fields=[
                make_field(
                    name="display_property",
                    default_value="$property(name)",
                    evaluator="maltego.replace",
                ),
            ],
        )
        assert _has_coalesce_display_property(entity) is False

    def test_no_properties(self):
        """Entity without properties returns False."""
        entity = V3EntityDefinition(
            id="maltego.Test",
            display_name="Test",
            display_name_plural="Tests",
            icon_resource="Phrase",
            properties=None,
        )
        assert _has_coalesce_display_property(entity) is False


class TestCapabilityNegotiatorCoalesce:
    """Test CapabilityNegotiator.supports_coalesce method."""

    def _make_negotiator(
        self,
        *,
        user_agent: str | None = None,
        client_id: str | None = None,
        client_version: str | None = None,
        header_caps: set | None = None,
    ) -> CapabilityNegotiator:
        """Create a CapabilityNegotiator for testing."""
        ua = MaltegoUserAgent(user_agent) if user_agent else None
        caps = set(c.id for c in (header_caps or set())) if header_caps else set()
        present = header_caps is not None
        mcc = MaltegoClientCapabilities(capabilities=caps, present=present)

        ctx = NegotiationContext(
            client_capabilities=mcc,
            protocol_version=None,
            client_id=client_id,
            client_version=Version(client_version) if client_version else None,
            user_agent=ua,
        )
        return CapabilityNegotiator(ctx)

    def test_web_client_supports_coalesce(self):
        """Web client (with header caps) supports coalesce."""
        from maltego.model.context import MaltegoCapability

        neg = self._make_negotiator(
            header_caps={MaltegoCapability.COMPOSITE_ENTITIES},
            client_id="Maltego Graph Browser",
            client_version="3.0.0",
        )
        assert neg.supports_coalesce() is True

    def test_no_context_defaults_to_support(self):
        """Without valid user agent or header caps, default to supporting coalesce."""
        # When there's no valid desktop UA and no header caps (browser headers),
        # we can't determine the client type so we default to support
        neg = self._make_negotiator(client_id="Maltego Desktop")
        # Without a valid UA, is_desktop() returns False, so supports_coalesce defaults to True
        assert neg.supports_coalesce() is True

    @pytest.mark.parametrize(
        "version,expected",
        [
            ("4.11.0", False),  # Below threshold
            ("9.9.8", False),  # Just below threshold
            ("9.9.9", True),  # Exactly at threshold
            ("10.0.0", True),  # Above threshold
        ],
    )
    def test_desktop_version_threshold(self, version: str, expected: bool):
        """Test desktop version threshold for coalesce support (COALESCE_MIN_DESKTOP = 9.9.9)."""
        neg = self._make_negotiator(
            user_agent=f"Maltego Desktop/{version} (Maltego One Eval; Mac OS X; 14.3; 0)"
        )
        assert neg.supports_coalesce() is expected


class TestParseEntityConfigOverridesJson:
    """Test parse_entity_config_overrides_json function."""

    def test_parse_valid_json(self):
        """Parse valid JSON array of rules."""
        json_str = """[
            {
                "entities": ["maltego.Entity1", "maltego.Entity2"],
                "clients": ["desktop"],
                "overrides": {"allowed_root": true}
            }
        ]"""
        result = parse_entity_config_overrides_json(json_str)
        assert len(result.rules) == 1
        assert result.rules[0].entities == ["maltego.Entity1", "maltego.Entity2"]
        assert result.rules[0].clients == ["desktop"]
        assert result.rules[0].overrides == {"allowed_root": True}

    def test_parse_multiple_rules(self):
        """Parse multiple rules."""
        json_str = """[
            {"entities": ["maltego.E1"], "clients": ["desktop"], "overrides": {"a": 1}},
            {"entities": ["maltego.E2"], "clients": ["web"], "overrides": {"b": 2}}
        ]"""
        result = parse_entity_config_overrides_json(json_str)
        assert len(result.rules) == 2

    def test_parse_field_override(self):
        """Parse field override with dot notation."""
        json_str = """[
            {
                "entities": ["maltego.Test"],
                "clients": ["desktop"],
                "overrides": {"fields.display_property.default_value": "$property(name)"}
            }
        ]"""
        result = parse_entity_config_overrides_json(json_str)
        assert result.rules[0].overrides == {
            "fields.display_property.default_value": "$property(name)"
        }

    def test_parse_invalid_json(self):
        """Invalid JSON raises ValueError."""
        with pytest.raises(ValueError, match="Invalid JSON"):
            parse_entity_config_overrides_json("not valid json")

    def test_parse_non_array(self):
        """Non-array JSON raises ValueError."""
        with pytest.raises(ValueError, match="must be an array"):
            parse_entity_config_overrides_json('{"entities": ["maltego.Test"]}')

    @pytest.mark.parametrize(
        "json_str,error_match",
        [
            ('[{"clients": ["desktop"], "overrides": {}}]', "'entities' must be an array"),
            ('[{"entities": ["maltego.Test"], "overrides": {}}]', "'clients' must be an array"),
            ('[{"entities": ["maltego.Test"], "clients": ["desktop"]}]', "'overrides' must be an object"),
        ],
    )
    def test_parse_missing_required_field(self, json_str: str, error_match: str):
        """Missing required fields raise ValueError."""
        with pytest.raises(ValueError, match=error_match):
            parse_entity_config_overrides_json(json_str)

    def test_parse_empty_array(self):
        """Empty array returns empty overrides."""
        result = parse_entity_config_overrides_json("[]")
        assert len(result.rules) == 0


class TestLoadEntityConfigOverridesFromEnv:
    """Test load_entity_config_overrides_from_env function."""

    def test_load_from_env(self, monkeypatch):
        """Load overrides from environment variable."""
        json_str = '[{"entities": ["maltego.Test"], "clients": ["desktop"], "overrides": {"allowed_root": true}}]'
        monkeypatch.setenv(ENTITY_CONFIG_OVERRIDES_ENV_VAR, json_str)
        result = load_entity_config_overrides_from_env()
        assert result is not None
        assert len(result.rules) == 1

    def test_no_env_var(self, monkeypatch):
        """Returns None when env var not set."""
        monkeypatch.delenv(ENTITY_CONFIG_OVERRIDES_ENV_VAR, raising=False)
        result = load_entity_config_overrides_from_env()
        assert result is None

    def test_empty_env_var(self, monkeypatch):
        """Returns None when env var is empty."""
        monkeypatch.setenv(ENTITY_CONFIG_OVERRIDES_ENV_VAR, "")
        result = load_entity_config_overrides_from_env()
        assert result is None

    def test_invalid_json_in_env(self, monkeypatch):
        """Returns None and logs warning when env var has invalid JSON."""
        monkeypatch.setenv(ENTITY_CONFIG_OVERRIDES_ENV_VAR, "not valid json")
        result = load_entity_config_overrides_from_env()
        assert result is None

    def test_ns_specific_env_var(self, monkeypatch):
        """Namespace-specific env var takes precedence over generic."""
        generic_json = '[{"entities": ["maltego.Generic"], "clients": ["desktop"], "overrides": {"a": 1}}]'
        specific_json = '[{"entities": ["maltego.Specific"], "clients": ["desktop"], "overrides": {"b": 2}}]'
        monkeypatch.setenv(ENTITY_CONFIG_OVERRIDES_ENV_VAR, generic_json)
        monkeypatch.setenv(
            "MALTEGO_SERVER_SANDBOX_ENTITY_CONFIG_OVERRIDES", specific_json
        )

        # ns="maltego.sandbox" -> strips "maltego." -> SANDBOX
        result = load_entity_config_overrides_from_env(ns="maltego.sandbox")
        assert result is not None
        assert len(result.rules) == 1
        assert result.rules[0].entities == ["maltego.Specific"]

    def test_ns_normalization(self, monkeypatch):
        """Namespace is normalized: 'maltego.' stripped, dots become underscores."""
        specific_json = '[{"entities": ["maltego.Test"], "clients": ["desktop"], "overrides": {"a": 1}}]'

        # ns="maltego.jinxpy_sentinel" -> JINXPY_SENTINEL (maltego. stripped)
        monkeypatch.setenv(
            "MALTEGO_SERVER_JINXPY_SENTINEL_ENTITY_CONFIG_OVERRIDES", specific_json
        )
        result = load_entity_config_overrides_from_env(ns="maltego.jinxpy_sentinel")
        assert result is not None

        # ns="com.example.transforms" -> COM_EXAMPLE_TRANSFORMS (dots to underscores)
        monkeypatch.delenv("MALTEGO_SERVER_JINXPY_SENTINEL_ENTITY_CONFIG_OVERRIDES")
        monkeypatch.setenv(
            "MALTEGO_SERVER_COM_EXAMPLE_TRANSFORMS_ENTITY_CONFIG_OVERRIDES",
            specific_json,
        )
        result = load_entity_config_overrides_from_env(ns="com.example.transforms")
        assert result is not None

    def test_fallback_to_generic_when_no_ns_specific(self, monkeypatch):
        """Falls back to generic env var when namespace-specific not set."""
        generic_json = '[{"entities": ["maltego.Generic"], "clients": ["desktop"], "overrides": {"a": 1}}]'
        monkeypatch.setenv(ENTITY_CONFIG_OVERRIDES_ENV_VAR, generic_json)
        monkeypatch.delenv(
            "MALTEGO_SERVER_SANDBOX_ENTITY_CONFIG_OVERRIDES", raising=False
        )

        result = load_entity_config_overrides_from_env(ns="maltego.sandbox")
        assert result is not None
        assert result.rules[0].entities == ["maltego.Generic"]

    def test_no_ns_uses_generic(self, monkeypatch):
        """Without ns, only checks generic env var."""
        generic_json = '[{"entities": ["maltego.Generic"], "clients": ["desktop"], "overrides": {"a": 1}}]'
        specific_json = '[{"entities": ["maltego.Specific"], "clients": ["desktop"], "overrides": {"b": 2}}]'
        monkeypatch.setenv(ENTITY_CONFIG_OVERRIDES_ENV_VAR, generic_json)
        monkeypatch.setenv(
            "MALTEGO_SERVER_SANDBOX_ENTITY_CONFIG_OVERRIDES", specific_json
        )

        # Without ns, should use generic
        result = load_entity_config_overrides_from_env()
        assert result is not None
        assert result.rules[0].entities == ["maltego.Generic"]


class TestMergeEntityConfigOverrides:
    """Test merge_entity_config_overrides function."""

    def test_merge_two_overrides(self):
        """Merge two overrides combines rules."""
        o1 = EntityConfigOverrides(
            rules=[
                EntityConfigOverride(
                    entities=["e1"], clients=["desktop"], overrides={"a": 1}
                )
            ]
        )
        o2 = EntityConfigOverrides(
            rules=[
                EntityConfigOverride(
                    entities=["e2"], clients=["web"], overrides={"b": 2}
                )
            ]
        )
        result = merge_entity_config_overrides(o1, o2)
        assert result is not None
        assert len(result.rules) == 2

    def test_merge_with_none(self):
        """Merge skips None values."""
        o1 = EntityConfigOverrides(
            rules=[
                EntityConfigOverride(
                    entities=["e1"], clients=["desktop"], overrides={"a": 1}
                )
            ]
        )
        result = merge_entity_config_overrides(None, o1, None)
        assert result is not None
        assert len(result.rules) == 1

    def test_merge_all_none(self):
        """Merge returns None when all inputs are None."""
        result = merge_entity_config_overrides(None, None)
        assert result is None

    def test_merge_empty(self):
        """Merge returns None when all inputs are empty."""
        result = merge_entity_config_overrides(
            EntityConfigOverrides(rules=[]),
            EntityConfigOverrides(rules=[]),
        )
        assert result is None
