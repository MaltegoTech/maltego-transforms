import pytest
from packaging.version import Version

from maltego.model.context import (
    MaltegoCapability,
    MaltegoClientCapabilities,
    MaltegoUserAgent,
)
from maltego.server.capability_matrix import CapabilityNegotiator, NegotiationContext
from tests.conftest import UA_4_10_0, UA_4_8_2, UA_5_0_0

pytestmark = pytest.mark.unit

UA_4_10_0_OBJECT = MaltegoUserAgent(UA_4_10_0["user-agent"])
UA_4_8_2_OBJECT = MaltegoUserAgent(UA_4_8_2["user-agent"])
UA_5_0_0_OBJECT = MaltegoUserAgent(UA_5_0_0["user-agent"])


def make_ctx(
        *,
        header_caps: set[MaltegoCapability] | None = None,
        protocol: str | None = None,
        client_id: str | None = None,
        client_version: str | None = None,
        ua: MaltegoUserAgent | None = None,
) -> NegotiationContext:
    caps = set(c.id for c in (header_caps or set()))
    present = header_caps is not None
    mcc = MaltegoClientCapabilities(capabilities=caps, present=present)
    return NegotiationContext(
        client_capabilities=mcc,
        protocol_version=protocol,
        client_id=client_id,
        client_version=Version(client_version) if client_version else None,
        user_agent=ua,
    )


def neg(**kwargs) -> CapabilityNegotiator:
    return CapabilityNegotiator(make_ctx(**kwargs))


C_INPUT = MaltegoCapability.INPUT_CONSTRAINTS
C_FLAT = MaltegoCapability.FLATTENED_COMPOSITE_ENTITIES
C_COMP = MaltegoCapability.COMPOSITE_ENTITIES


@pytest.mark.parametrize(
    "label,kwargs,expect",
    [
        (
                "no-header, no-proto, desktop-4.12",
                dict(header_caps=None, protocol=None, client_id="Maltego Desktop", client_version="4.12.0"),
                {C_INPUT: True, C_FLAT: False, C_COMP: False},
        ),
        (
                "no-header, proto-3.0, desktop-4.12",
                dict(header_caps=None, protocol="3.0", client_id="Maltego Desktop", client_version="4.12.0"),
                {C_INPUT: True, C_FLAT: False, C_COMP: False},
        ),
        (
                "header-composite, proto-3.2",
                dict(header_caps={C_COMP}, protocol="3.2", client_id="Maltego Desktop", client_version="4.12.0"),
                {C_INPUT: False, C_FLAT: False, C_COMP: True},
        ),
        (
                "header-composite, proto-3.1",
                dict(header_caps={C_COMP}, protocol="3.1", client_id="Maltego Desktop", client_version="4.12.0"),
                {C_INPUT: False, C_FLAT: False, C_COMP: False},
        ),
        # (
        #         "graph-browser, no-header",
        #         dict(header_caps=None, protocol="3.2", client_id="Maltego Graph Browser", client_version="9.9.9"),
        #         {C_INPUT: False, C_FLAT: False, C_COMP: False},
        # ),
        (
                "ua-fallback-4.10",
                dict(header_caps=None, protocol=None, ua=UA_4_10_0_OBJECT),
                {C_INPUT: True, C_FLAT: False, C_COMP: False},
        ),
        (
                "empty-header, proto-3.2",
                dict(header_caps=set(), protocol="3.2", client_id="Maltego Desktop", client_version="4.12.0"),
                {C_INPUT: False, C_FLAT: False, C_COMP: False},
        ),
    ],
)
def test_check_capabilities(label, kwargs, expect):
    n = neg(**kwargs)
    assert n._check_capability(C_INPUT) == expect[C_INPUT], f"{label}: InputConstraints"
    assert n._check_capability(C_FLAT) == expect[C_FLAT], f"{label}: FlattenedCompositeEntities"
    assert n._check_capability(C_COMP) == expect[C_COMP], f"{label}: CompositeEntities"


class TxComposite:
    input_constraint = None
    interactive = False
    composite_entities = True


class TxInteractive:
    input_constraint = None
    interactive = True
    composite_entities = False


class TxMixed:
    input_constraint = object()
    interactive = True
    composite_entities = True


def test_allows_transform_no_negotiation_hints_allows():
    n = neg(header_caps=None, protocol=None, client_id=None, client_version=None, ua=None)

    class TxAny:
        input_constraint = object()
        interactive = True
        composite_entities = True

    assert n.allows_transform(TxAny()) is True


def test_allows_transform_composite_requires_header_and_proto_gate():
    n_yes = neg(header_caps={C_COMP}, protocol="3.2", client_id="Maltego Desktop", client_version="4.12.0")
    assert n_yes.allows_transform(TxComposite()) is True

    n_no = neg(header_caps={C_COMP}, protocol="3.1", client_id="Maltego Desktop", client_version="4.12.0")
    assert n_no.allows_transform(TxComposite()) is False

    n_nohdr = neg(header_caps=None, protocol="3.2", client_id="Maltego Desktop", client_version="4.12.0")
    assert n_nohdr.allows_transform(TxComposite()) is False


def test_allows_transform_interactive_and_input_constraints_by_version_or_header():
    n = neg(header_caps=None, protocol=None, client_id="Maltego Desktop", client_version="4.12.0")
    assert n.allows_transform(TxInteractive()) is True
    assert n.allows_transform(TxMixed()) is False

    n_hdr = neg(header_caps={C_INPUT}, protocol=None, client_id="Maltego Desktop", client_version="4.12.0")
    assert n_hdr.allows_transform(TxInteractive()) is False

    n_hdr2 = neg(header_caps={C_INPUT, MaltegoCapability.MULTI_CHOICE_CONTROLS}, protocol=None)
    assert n_hdr2.allows_transform(TxMixed()) is False


class NoCapsMachine:
    input_constraints = False
    interactive = False
    composite_entities = False


class InteractiveMachine:
    input_constraints = False
    interactive = True
    composite_entities = False


class CompositeMachine:
    input_constraints = False
    interactive = False
    composite_entities = True


class MixedMachine:
    input_constraints = True
    interactive = True
    composite_entities = True


def test_allows_machine_paths():
    n = neg(header_caps=None, protocol=None)
    assert n.allows_machine(NoCapsMachine) is True

    n_v = neg(header_caps=None, client_id="Maltego Desktop", client_version="4.7.2")
    assert n_v.allows_machine(InteractiveMachine) is True
    n_vlow = neg(header_caps=None, client_id="Maltego Desktop", client_version="4.7.1")
    assert n_vlow.allows_machine(InteractiveMachine) is False

    n_comp_yes = neg(header_caps={C_COMP}, protocol="3.2")
    assert n_comp_yes.allows_machine(CompositeMachine) is True
    n_comp_no = neg(header_caps=None, protocol="3.2")
    assert n_comp_no.allows_machine(CompositeMachine) is False

    n_mixed_no = neg(header_caps=None, client_id="Maltego Desktop", client_version="4.12.0", protocol="3.2")
    assert n_mixed_no.allows_machine(MixedMachine) is False
    n_mixed_yes = neg(header_caps={C_INPUT, MaltegoCapability.MULTI_CHOICE_CONTROLS, C_COMP}, protocol="3.2")
    assert n_mixed_yes.allows_machine(MixedMachine) is True


def test_flattened_disabled_without_header():
    caps = MaltegoClientCapabilities(set(), present=False)
    ctx = NegotiationContext(client_capabilities=caps, protocol_version=None,
                             client_id="Maltego Desktop", client_version=Version("4.12.0"))
    resolved = CapabilityNegotiator(ctx).resolved
    assert not resolved.flattened_composite_entities


def test_flattened_allowed_with_header():
    caps = MaltegoClientCapabilities({MaltegoCapability.FLATTENED_COMPOSITE_ENTITIES.id}, present=True)
    ctx = NegotiationContext(client_capabilities=caps, protocol_version=None)
    resolved = CapabilityNegotiator(ctx).resolved
    assert resolved.flattened_composite_entities


class ConstraintTx:
    """Minimal transform shell with a pluggable constraint tree."""
    interactive = False
    composite_entities = False

    def __init__(self, constraint):
        self.input_constraint = constraint


class ConstraintNode:
    def __init__(self, type_id: str, children: list["ConstraintNode"] | None = None):
        self.type = type_id
        if children is not None:
            self.constraints = children


KNOWN_LEAF = "property_value_equals"
KNOWN_COMPOSITE = "property_satisfies_all"
UNKNOWN_LEAF = "totally_new_constraint_type"
UNKNOWN_COMPOSITE = "super_new_composite_constraint"


def known_tree():
    return ConstraintNode(KNOWN_COMPOSITE, [
        ConstraintNode(KNOWN_LEAF),
        ConstraintNode(KNOWN_LEAF),
    ])


def mixed_tree_with_unknown():
    return ConstraintNode(KNOWN_COMPOSITE, [
        ConstraintNode(KNOWN_LEAF),
        ConstraintNode(UNKNOWN_LEAF),
    ])


def unknown_only_tree():
    return ConstraintNode(UNKNOWN_COMPOSITE, [
        ConstraintNode(UNKNOWN_LEAF),
    ])


def test_browser_with_cap_header_never_filters_unknown_constraints():
    n = neg(header_caps={MaltegoCapability.INPUT_CONSTRAINTS})
    assert n.allows_transform(ConstraintTx(unknown_only_tree())) is True


def test_browser_with_header_or_identifier():
    n = neg(header_caps=None, client_id="Maltego Graph Browser", client_version="9.9.9")
    assert n.header_is_authoritative() is False
    n_with_caps = neg(header_caps={MaltegoCapability.INPUT_CONSTRAINTS},
                      client_id="Maltego Graph Browser", client_version="9.9.9")
    assert n_with_caps.allows_transform(ConstraintTx(unknown_only_tree())) is True

    # Without header caps, capability gate fails (expected), but this is not "filtering unknowns".
    assert n.allows_transform(ConstraintTx(unknown_only_tree())) is False


def test_desktop_older_than_4_10_rejects_all_input_constraints():
    n = neg(header_caps=None, ua=UA_4_8_2_OBJECT)
    assert n.allows_transform(ConstraintTx(known_tree())) is False
    assert n.allows_transform(ConstraintTx(unknown_only_tree())) is False


def test_desktop_4_10_filter_unknown_but_allow_known():
    n = neg(header_caps=None, ua=UA_4_10_0_OBJECT)

    # Known tree passes
    assert n.allows_transform(ConstraintTx(known_tree())) is True

    # Mixed or unknown-only trees are filtered
    assert n.allows_transform(ConstraintTx(mixed_tree_with_unknown())) is False
    assert n.allows_transform(ConstraintTx(unknown_only_tree())) is False


def test_desktop_5_0_allows_unknown_constraints():
    n = neg(header_caps=None, ua=UA_5_0_0_OBJECT)

    assert n._check_capability(MaltegoCapability.INPUT_CONSTRAINTS_UNKNOWN_SAFE) is True

    txs = [
        ConstraintTx(known_tree()),
        ConstraintTx(mixed_tree_with_unknown()),
        ConstraintTx(unknown_only_tree()),
    ]
    allowed = [t for t in txs if n.allows_transform(t)]
    assert len(allowed) == len(txs), "Desktop >= 5.0.0 must not filter unknown constraints"


@pytest.mark.parametrize(
    "ua_obj, expect_input_cap",
    [
        (UA_4_8_2_OBJECT, False),
        (UA_4_10_0_OBJECT, True),
        (UA_5_0_0_OBJECT, True),
    ],
)
def test_desktop_input_constraints_capability_by_ua(ua_obj, expect_input_cap):
    n = neg(header_caps=None, ua=ua_obj)
    assert n._check_capability(MaltegoCapability.INPUT_CONSTRAINTS) is expect_input_cap
