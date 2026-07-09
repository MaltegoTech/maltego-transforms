from typing import List

from maltego.entities import Phrase

from maltego.model.entity import MaltegoEntity, OverlayPositions, OverlayTypes
from maltego.model.link import MaltegoLinkProperty
from maltego.model.types import LinkColor, LinkStyle, LinkThickness
from maltego.server import MaltegoContext, register_transform

TRANSFORM_SET = "New Maltego Integration"


@register_transform(
    display_name="Add All Color Overlays [New Maltego Integration]",
    description="Transform that adds a color overlay in every possible orientation",
    transform_set=TRANSFORM_SET,
)
async def color_overlays(
    input_entity: MaltegoEntity,
) -> MaltegoEntity:
    input_entity.set_property("green", "green", display_name="green")
    input_entity.set_property("blue", "blue", display_name="blue")
    input_entity.set_property("red", "red", display_name="red")
    input_entity.add_overlay(OverlayTypes.COLOR, OverlayPositions.CENTER, "green")
    input_entity.add_overlay(OverlayTypes.COLOR, OverlayPositions.NORTH, "blue")
    input_entity.add_overlay(OverlayTypes.COLOR, OverlayPositions.NORTHWEST, "red")
    input_entity.add_overlay(OverlayTypes.COLOR, OverlayPositions.SOUTH, "green")
    input_entity.add_overlay(OverlayTypes.COLOR, OverlayPositions.SOUTHWEST, "blue")
    input_entity.add_overlay(OverlayTypes.COLOR, OverlayPositions.WEST, "red")
    return input_entity


@register_transform(
    display_name="Add All Text Overlays [New Maltego Integration]",
    description="Transform that adds a string overlay in every possible orientation",
    transform_set=TRANSFORM_SET,
)
async def text_overlays(
    input_entity: MaltegoEntity,
) -> MaltegoEntity:
    input_entity.set_property("string1", "1", display_name="string1")
    input_entity.set_property("string2", "2", display_name="string2")
    input_entity.set_property("string3", "3", display_name="string3")
    input_entity.set_property("string4", "4", display_name="string4")
    input_entity.set_property("string5", "5", display_name="string5")
    input_entity.set_property("string6", "6", display_name="string6")
    input_entity.add_overlay(OverlayTypes.TEXT, OverlayPositions.CENTER, "string1")
    input_entity.add_overlay(OverlayTypes.TEXT, OverlayPositions.NORTH, "string2")
    input_entity.add_overlay(OverlayTypes.TEXT, OverlayPositions.NORTHWEST, "string3")
    input_entity.add_overlay(OverlayTypes.TEXT, OverlayPositions.SOUTH, "string4")
    input_entity.add_overlay(OverlayTypes.TEXT, OverlayPositions.SOUTHWEST, "string5")
    input_entity.add_overlay(OverlayTypes.TEXT, OverlayPositions.WEST, "string6")
    return input_entity


@register_transform(
    display_name="Add All Image Overlays [New Maltego Integration]",
    description="Transform that adds a image overlay in every possible orientation",
    transform_set=TRANSFORM_SET,
)
async def image_overlays(
    input_entity: MaltegoEntity,
) -> MaltegoEntity:
    input_entity.set_property(
        "image", "https://www.maltego.com/favicon.ico", display_name="image"
    )
    input_entity.add_overlay(OverlayTypes.IMAGE, OverlayPositions.CENTER, "image")
    input_entity.add_overlay(OverlayTypes.IMAGE, OverlayPositions.NORTH, "image")
    input_entity.add_overlay(OverlayTypes.IMAGE, OverlayPositions.NORTHWEST, "image")
    input_entity.add_overlay(OverlayTypes.IMAGE, OverlayPositions.SOUTH, "image")
    input_entity.add_overlay(OverlayTypes.IMAGE, OverlayPositions.SOUTHWEST, "image")
    input_entity.add_overlay(OverlayTypes.IMAGE, OverlayPositions.WEST, "image")
    return input_entity


@register_transform(
    display_name="Link Properties on Entity [New Maltego Integration]",
    description="Creates an entity with custom link styling",
    transform_set=TRANSFORM_SET,
)
async def link_on_entity_example(input_entity: Phrase) -> Phrase:
    """
    Demonstrates setting link properties directly on entity creation.
    The link connects the new entity back to the input entity.
    """
    return Phrase(
        f"Connected to {input_entity.value}",
        reverse_link=True,  # Arrow points to parent (input entity)
        link_thickness=LinkThickness.THICKNESS_4,
        link_style=LinkStyle.DOTTED,
        link_color=LinkColor.RED,
        link_label="related to",
    )


@register_transform(
    display_name="Link via Graph API [New Maltego Integration]",
    description="Creates entities and links them using the graph API",
    transform_set=TRANSFORM_SET,
)
async def link_via_graph_example(input_entity: Phrase, context: MaltegoContext) -> None:
    """
    Demonstrates adding links explicitly using graph.add_link().
    This gives more control over link properties and direction.
    """
    graph = context.graph

    # Add child entities
    child1 = graph.add_entity(Phrase("Child 1"))
    child2 = graph.add_entity(Phrase("Child 2"))

    graph.add_link(
        input_entity,
        child1,
        is_reversed=False,  # Arrow points from input to child
        thickness=LinkThickness.THICKNESS_3,
        style=LinkStyle.DASHED,
        color=LinkColor.BLUE,
        label="parent of",
    )

    graph.add_link(
        input_entity,
        child2,
        is_reversed=True,
        thickness=LinkThickness.THICKNESS_2,
        style=LinkStyle.DASHDOT,
        color=LinkColor.GREEN,
        label="child of",
    )

    return None  # Return None when using graph directly


@register_transform(
    display_name="Custom Link Properties [New Maltego Integration]",
    description="Creates links with custom metadata properties",
    transform_set=TRANSFORM_SET,
)
async def custom_link_properties_example(
    input_entity: Phrase, context: MaltegoContext
) -> None:
    """
    Demonstrates adding custom properties to links.
    Link properties appear in the link details panel.
    """
    graph = context.graph

    target = graph.add_entity(Phrase("Target Entity"))

    # Add link with custom properties
    graph.add_link(
        input_entity,
        target,
        thickness=LinkThickness.THICKNESS_2,
        color=LinkColor.PURPLE,
        label="analyzed",
        properties={
            "confidence": MaltegoLinkProperty(
                name="confidence",
                value="0.95",
                display_name="Confidence Score",
            ),
            "source": MaltegoLinkProperty(
                name="source",
                value="API Analysis",
                display_name="Data Source",
            ),
            "timestamp": MaltegoLinkProperty(
                name="timestamp",
                value="2024-01-15T10:30:00Z",
                display_name="Analysis Time",
            ),
        },
    )

    return None


@register_transform(
    display_name="Entity Notes [New Maltego Integration]",
    description="Adds notes to entities",
    transform_set=TRANSFORM_SET,
)
async def entity_notes_example(input_entity: Phrase) -> Phrase:
    """
    Demonstrates adding text notes to entities.
    Notes appear in the entity details panel.
    """
    result = Phrase(f"Analyzed: {input_entity.value}")

    # Set the note
    result.note = "This entity was discovered through API analysis.\n"
    result.note += "Additional details:\n"
    result.note += "- Source: External Database\n"
    result.note += "- Confidence: High\n"
    result.note += "- Last Updated: 2024-01-15"

    return result


@register_transform(
    display_name="Entity Weights [New Maltego Integration]",
    description="Returns entities with different weights for ranking",
    transform_set=TRANSFORM_SET,
)
async def entity_weight_example(input_entity: Phrase) -> List[Phrase]:
    """
    Demonstrates entity weights for importance ranking.
    """
    return [
        Phrase("Critical finding", weight=1000),
        Phrase("High importance", weight=500),
        Phrase("Medium importance", weight=100),
        Phrase("Low importance", weight=10),
        Phrase("Minimal importance", weight=1),
    ]
