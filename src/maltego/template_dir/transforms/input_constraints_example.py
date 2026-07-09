from maltego.entities import Domain, Person, Phrase

from maltego.model.input_constraints import (
    # String match types
    ConstraintStringMatchType,
    EntityHasPropertySatisfying,  # Entity must have property matching constraint
    # Entity-level constraints
    EntitySatisfiesAll,  # All constraints must match (AND)
    EntitySatisfiesAny,  # At least one constraint must match (OR)
    EntitySatisfiesNone,  # No constraints must match (NOT)
    EntityTypeConstraint,  # Match specific entity type
    PropertyNameEquals,  # Property name matches
    # Property-level constraints
    PropertySatisfiesAll,  # All property constraints must match
    PropertyTypeEquals,  # Property type matches (STRING, INT, DATE, etc.)
    PropertyValueEquals,  # Property value exact match
    PropertyValueMatchesRegex,  # Property value regex match
    PropertyValueStringMatch,  # Property value string matching (contains, startswith, etc.)
)
from maltego.server import MaltegoEntity, register_transform

TRANSFORM_SET = "New Maltego Integration"


@register_transform(
    display_name="Domain Only Transform [New Maltego Integration]",
    description="Only available on Domain entities",
    transform_set=TRANSFORM_SET,
    input_constraint=EntityTypeConstraint(entity_type="maltego.Domain"),
)
async def domain_only_transform(input_entity: Domain) -> Phrase:
    """
    This transform only appears for Domain entities.

    EntityTypeConstraint uses the full entity type name (e.g., "maltego.Domain").
    """
    return Phrase(f"Domain: {input_entity.value}")


@register_transform(
    display_name="Multiple Entity Types [New Maltego Integration]",
    description="Available on Domain OR Person entities",
    transform_set=TRANSFORM_SET,
    input_constraint=EntitySatisfiesAny(
        constraints=[
            EntityTypeConstraint(entity_type="maltego.Domain"),
            EntityTypeConstraint(entity_type="maltego.Person"),
        ]
    ),
)
async def multiple_entity_types_transform(input_entity: MaltegoEntity) -> Phrase:
    """
    This transform appears for Domain OR Person entities.
    """
    return Phrase(f"Value: {input_entity.value}")


@register_transform(
    display_name="Property Exists [New Maltego Integration]",
    description="Only for entities with an 'email' property",
    transform_set=TRANSFORM_SET,
    input_constraint=EntityHasPropertySatisfying(
        constraint=PropertySatisfiesAll(constraints=[PropertyNameEquals(value="email")])
    ),
)
async def property_exists_transform(input_entity: MaltegoEntity) -> Phrase:
    """
    This transform only appears for entities that have an 'email' property.
    """
    email = input_entity.get_property("email")
    return Phrase(f"Email: {email}")


@register_transform(
    display_name="Property Value Match [New Maltego Integration]",
    description="Only for Person entities where firstnames='John'",
    transform_set=TRANSFORM_SET,
    input_constraint=EntitySatisfiesAll(
        constraints=[
            EntityTypeConstraint(entity_type="maltego.Person"),
            EntityHasPropertySatisfying(
                constraint=PropertySatisfiesAll(
                    constraints=[
                        PropertyNameEquals(value="person.firstnames"),
                        PropertyValueEquals(value="John", ignore_case=True),
                    ]
                )
            ),
        ]
    ),
)
async def property_value_match_transform(input_entity: Person) -> Phrase:
    """
    This transform only appears for Person entities where firstnames='John'.

    Set ignore_case=True for case-insensitive comparison.
    """
    return Phrase(f"Hello {input_entity.value}!")


@register_transform(
    display_name="Property String Pattern [New Maltego Integration]",
    description="Only for entities where domain starts with 'www.'",
    transform_set=TRANSFORM_SET,
    input_constraint=EntitySatisfiesAll(
        constraints=[
            EntityTypeConstraint(entity_type="maltego.Domain"),
            EntityHasPropertySatisfying(
                constraint=PropertySatisfiesAll(
                    constraints=[
                        PropertyNameEquals(value="fqdn"),
                        PropertyValueStringMatch(
                            value="www.",
                            ignore_case=True,
                            match_type=ConstraintStringMatchType.STARTSWITH,
                        ),
                    ]
                )
            ),
        ]
    ),
)
async def string_pattern_transform(input_entity: Domain) -> Phrase:
    """
    This transform only appears for Domain entities where fqdn starts with 'www.'.
    """
    return Phrase(f"WWW domain: {input_entity.value}")


@register_transform(
    display_name="Regex Match [New Maltego Integration]",
    description="Only for domains matching valid FQDN pattern",
    transform_set=TRANSFORM_SET,
    input_constraint=EntitySatisfiesAll(
        constraints=[
            EntityTypeConstraint(entity_type="maltego.Domain"),
            EntityHasPropertySatisfying(
                constraint=PropertySatisfiesAll(
                    constraints=[
                        PropertyValueMatchesRegex(
                            regex=r"^(?!-)[A-Za-z0-9-]{1,63}\.[A-Za-z]{2,6}$"
                        )
                    ]
                )
            ),
        ]
    ),
)
async def regex_match_transform(input_entity: Domain) -> Phrase:
    """
    This transform uses regex to validate the domain format.
    """
    return Phrase(f"Valid domain: {input_entity.value}")


@register_transform(
    display_name="NOT Constraint [New Maltego Integration]",
    description="For Domain entities that do NOT start with 'localhost'",
    transform_set=TRANSFORM_SET,
    input_constraint=EntitySatisfiesAll(
        constraints=[
            EntityTypeConstraint(entity_type="maltego.Domain"),
            EntitySatisfiesNone(
                constraints=[
                    EntityHasPropertySatisfying(
                        constraint=PropertySatisfiesAll(
                            constraints=[
                                PropertyNameEquals(value="fqdn"),
                                PropertyValueStringMatch(
                                    value="localhost",
                                    match_type=ConstraintStringMatchType.STARTSWITH,
                                ),
                            ]
                        )
                    ),
                ]
            ),
        ]
    ),
)
async def not_constraint_transform(input_entity: Domain) -> Phrase:
    """
    This transform appears for Domain entities that do NOT start with 'localhost'.
    """
    return Phrase(f"Remote domain: {input_entity.value}")


@register_transform(
    display_name="Property Type Check [New Maltego Integration]",
    description="Only for entities with an INT type property",
    transform_set=TRANSFORM_SET,
    input_constraint=EntityHasPropertySatisfying(
        constraint=PropertySatisfiesAll(constraints=[PropertyTypeEquals(value="INT")])
    ),
)
async def property_type_transform(input_entity: MaltegoEntity) -> Phrase:
    """
    This transform only appears for entities with an INT-type property.
    """
    return Phrase(f"Has int property: {input_entity.value}")


@register_transform(
    display_name="Complex Combined Constraint [New Maltego Integration]",
    description="Domain entities that are .com OR .org",
    transform_set=TRANSFORM_SET,
    input_constraint=EntitySatisfiesAll(
        constraints=[
            # Must be a Domain
            EntityTypeConstraint(entity_type="maltego.Domain"),
            # AND must end with .com OR .org
            EntitySatisfiesAny(
                constraints=[
                    EntityHasPropertySatisfying(
                        constraint=PropertySatisfiesAll(
                            constraints=[
                                PropertyNameEquals(value="fqdn"),
                                PropertyValueStringMatch(
                                    value=".com",
                                    match_type=ConstraintStringMatchType.ENDSWITH,
                                    ignore_case=True,
                                ),
                            ]
                        )
                    ),
                    EntityHasPropertySatisfying(
                        constraint=PropertySatisfiesAll(
                            constraints=[
                                PropertyNameEquals(value="fqdn"),
                                PropertyValueStringMatch(
                                    value=".org",
                                    match_type=ConstraintStringMatchType.ENDSWITH,
                                    ignore_case=True,
                                ),
                            ]
                        )
                    ),
                ]
            ),
        ]
    ),
)
async def complex_constraint_transform(input_entity: Domain) -> Phrase:
    """
    This transform demonstrates combining multiple constraint types.
    """
    return Phrase(f"Commercial/Org domain: {input_entity.value}")


if __name__ == "__main__":
    from maltego.server import MaltegoServerSettings, run_server

    server_settings = MaltegoServerSettings(
        server_name="Maltego Transform Server", ns="acme", author="Acme"
    )
    run_server(
        host="127.0.0.1",
        port=8080,
        ssl=False,
        settings=server_settings,
        log_level="INFO",
    )
