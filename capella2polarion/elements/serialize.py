# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Objects for serialization of capella objects to workitems."""
from __future__ import annotations

import base64
import collections
import collections.abc as cabc
import logging
import mimetypes
import pathlib
import re
import typing as t

import markupsafe
import polarion_rest_api_client as polarion_api
from capellambse import helpers as chelpers
from capellambse.model import common
from capellambse.model import diagram as diagr
from capellambse.model.crosslayer import capellacore, cs, interaction
from capellambse.model.layers import oa, pa
from lxml import etree

from capella2polarion.elements import helpers

RE_DESCR_LINK_PATTERN = re.compile(r"<a href=\"hlink://([^\"]+)\">[^<]+<\/a>")
RE_DESCR_DELETED_PATTERN = re.compile(
    f"<deleted element ({chelpers.RE_VALID_UUID.pattern})>"
)
RE_CAMEL_CASE_2ND_WORD_PATTERN = re.compile(r"([a-z]+)([A-Z][a-z]+)")
DIAGRAM_STYLES = {"max-width": "100%"}

PrePostConditionElement = t.Union[
    oa.OperationalCapability, interaction.Scenario
]

logger = logging.getLogger(__name__)


class CapellaWorkItem(polarion_api.WorkItem):
    """A custom WorkItem class with additional capella related attributes."""

    class Condition(t.TypedDict):
        """A class to describe a pre or post condition."""

        type: str
        value: str

    uuid_capella: str | None
    preCondition: Condition | None
    postCondition: Condition | None


def element(
    obj: diagr.Diagram | common.GenericElement,
    ctx: dict[str, t.Any],
    serializer: cabc.Callable[[t.Any, dict[str, t.Any]], CapellaWorkItem],
) -> CapellaWorkItem | None:
    """Seralize a Capella element for the PolarionRestAPI."""
    try:
        return serializer(obj, ctx)
    except Exception as error:
        logger.error("Serializing model element failed. %s", error.args[0])
        return None


def diagram(diag: diagr.Diagram, ctx: dict[str, t.Any]) -> CapellaWorkItem:
    """Serialize a diagram for Polarion."""
    diagram_path = ctx["DIAGRAM_CACHE"] / f"{diag.uuid}.svg"
    src = _decode_diagram(diagram_path)
    style = "; ".join(
        (f"{key}: {value}" for key, value in DIAGRAM_STYLES.items())
    )
    description = f'<html><p><img style="{style}" src="{src}" /></p></html>'
    return CapellaWorkItem(
        type="diagram",
        title=diag.name,
        description_type="text/html",
        description=description,
        status="open",
        uuid_capella=diag.uuid,
    )


def _decode_diagram(diagram_path: pathlib.Path) -> str:
    mime_type, _ = mimetypes.guess_type(diagram_path)
    if mime_type is None:
        logger.error(
            "Do not understand the MIME subtype for the diagram '%s'!",
            diagram_path,
        )
        return ""
    content = diagram_path.read_bytes()
    content_encoded = base64.standard_b64encode(content)
    assert mime_type is not None
    image_data = b"data:" + mime_type.encode() + b";base64," + content_encoded
    src = image_data.decode()
    return src


def generic_work_item(
    obj: common.GenericElement, ctx: dict[str, t.Any]
) -> CapellaWorkItem:
    """Return a work item for the given model element."""
    xtype = ctx["POLARION_TYPE_MAP"].get(obj.uuid, type(obj).__name__)
    serializer = SERIALIZERS.get(xtype, _generic_work_item)
    return serializer(obj, ctx)


def _generic_work_item(
    obj: common.GenericElement, ctx: dict[str, t.Any]
) -> CapellaWorkItem:
    xtype = ctx["POLARION_TYPE_MAP"].get(obj.uuid, type(obj).__name__)
    raw_description = getattr(obj, "description", markupsafe.Markup(""))
    uuids, value = _sanitize_description(raw_description, ctx)
    ctx.setdefault("DESCR_REFERENCES", {})[obj.uuid] = uuids
    requirement_types = _get_requirement_types_text(obj)
    return CapellaWorkItem(
        type=helpers.resolve_element_type(xtype),
        title=obj.name,
        description_type="text/html",
        description=value,
        status="open",
        uuid_capella=obj.uuid,
        **requirement_types,
    )


def _get_requirement_types_text(
    obj: common.GenericElement,
) -> dict[str, dict[str, str]]:
    type_texts = collections.defaultdict(list)
    for req in obj.requirements:
        if req is None:
            logger.error(
                "RequirementsRelation with broken target found %r", obj.name
            )
            continue

        if not (req.type and req.text):
            continue

        type_texts[req.type.long_name].append(req.text)
    return _format_texts(type_texts)


def _format_texts(
    type_texts: dict[str, list[str]]
) -> dict[str, dict[str, str]]:
    def _format(texts: list[str]) -> dict[str, str]:
        if len(texts) > 1:
            items = "".join(f"<li>{text}</li>" for text in texts)
            text = f"<ul>{items}</ul>"
        else:
            text = texts[0]
        return {"type": "text/html", "value": text}

    requirement_types = {}
    for typ, texts in type_texts.items():
        requirement_types[typ.lower()] = _format(texts)
    return requirement_types


def _sanitize_description(
    descr: markupsafe.Markup, ctx: dict[str, t.Any]
) -> tuple[list[str], markupsafe.Markup]:
    referenced_uuids: list[str] = []
    replaced_markup = RE_DESCR_LINK_PATTERN.sub(
        lambda match: replace_markup(match, ctx, referenced_uuids), descr
    )

    def repair_images(node: etree._Element) -> None:
        if node.tag != "img":
            return

        file_url = pathlib.PurePosixPath(node.get("src"))
        workspace = file_url.parts[0]
        file_path = pathlib.PurePosixPath(*file_url.parts[1:])
        mime_type, _ = mimetypes.guess_type(file_url)
        resources = ctx["MODEL"]._loader.resources
        filehandler = resources[["\x00", workspace][workspace in resources]]
        try:
            with filehandler.open(file_path, "r") as img:
                b64_img = base64.b64encode(img.read()).decode("utf8")
                node.attrib["src"] = f"data:{mime_type};base64,{b64_img}"
        except FileNotFoundError:
            logger.error("Inline image can't be found from %r", file_path)

    repaired_markup = chelpers.process_html_fragments(
        replaced_markup, repair_images
    )
    return referenced_uuids, repaired_markup


def replace_markup(
    match: re.Match,
    ctx: dict[str, t.Any],
    referenced_uuids: list[str],
    non_matcher: cabc.Callable[[str], str] = lambda i: i,
) -> str:
    """Replace UUID references in a ``match`` with a work item link.

    If the UUID doesn't correspond to an existing work item the original
    text is returned.
    """
    uuid = match.group(1)
    if pid := ctx["POLARION_ID_MAP"].get(uuid):
        referenced_uuids.append(uuid)
        return (
            '<span class="polarion-rte-link" data-type="workItem" '
            f'id="fake" data-item-id="{pid}" data-option-id="long">'
            "</span>"
        )
    return non_matcher(match.group(0))


def include_pre_and_post_condition(
    obj: PrePostConditionElement, ctx: dict[str, t.Any]
) -> CapellaWorkItem:
    """Return generic attributes and pre- plus post-condition."""

    def get_condition(cap: PrePostConditionElement, name: str) -> str:
        if not (condition := getattr(cap, name)):
            return ""
        return condition.specification["capella:linkedText"].striptags()

    def strike_through(string: str) -> str:
        if match := RE_DESCR_DELETED_PATTERN.match(string):
            string = match.group(1)
        return f'<span style="text-decoration: line-through;">{string}</span>'

    def matcher(match: re.Match) -> str:
        return strike_through(replace_markup(match, ctx, []))

    work_item = _generic_work_item(obj, ctx)
    pre_condition = RE_DESCR_DELETED_PATTERN.sub(
        matcher, get_condition(obj, "precondition")
    )
    post_condition = RE_DESCR_DELETED_PATTERN.sub(
        matcher, get_condition(obj, "postcondition")
    )

    work_item.preCondition = _condition(True, pre_condition)
    work_item.postCondition = _condition(True, post_condition)

    return work_item


def get_linked_text(
    obj: capellacore.Constraint, ctx: dict[str, t.Any]
) -> markupsafe.Markup:
    """Return sanitized markup of the given ``obj`` linked text."""
    description = obj.specification["capella:linkedText"].striptags()
    uuids, value = _sanitize_description(description, ctx)
    if uuids:
        ctx.setdefault("DESCR_REFERENCES", {})[obj.uuid] = uuids
    return value


def constraint(
    obj: capellacore.Constraint, ctx: dict[str, t.Any]
) -> CapellaWorkItem:
    """Return attributes for a ``Constraint``."""
    work_item = _generic_work_item(obj, ctx)
    work_item.description = (  # pylint: disable=attribute-defined-outside-init
        get_linked_text(obj, ctx)
    )
    return work_item


def _condition(html: bool, value: str) -> CapellaWorkItem.Condition:
    _type = "text/html" if html else "text/plain"
    return {"type": _type, "value": value}


def component_or_actor(
    obj: cs.Component, ctx: dict[str, t.Any]
) -> CapellaWorkItem:
    """Return attributes for a ``Component``."""
    work_item = _generic_work_item(obj, ctx)
    if obj.is_actor:
        xtype = RE_CAMEL_CASE_2ND_WORD_PATTERN.sub(
            r"\1Actor", type(obj).__name__
        )
        work_item.type = helpers.resolve_element_type(  # pylint: disable=attribute-defined-outside-init
            xtype
        )
    return work_item


def physical_component(
    obj: pa.PhysicalComponent, ctx: dict[str, t.Any]
) -> CapellaWorkItem:
    """Return attributes for a ``PhysicalComponent``."""
    work_item = component_or_actor(obj, ctx)
    xtype = work_item.type
    if obj.nature is not None:
        work_item.type = f"{xtype}{obj.nature.name.capitalize()}"  # pylint: disable=attribute-defined-outside-init
    return work_item


Serializer = cabc.Callable[
    [common.GenericElement, dict[str, t.Any]], CapellaWorkItem
]
SERIALIZERS: dict[str, Serializer] = {
    "CapabilityRealization": include_pre_and_post_condition,
    "LogicalComponent": component_or_actor,
    "OperationalCapability": include_pre_and_post_condition,
    "PhysicalComponent": physical_component,
    "SystemComponent": component_or_actor,
    "Scenario": include_pre_and_post_condition,
    "Constraint": constraint,
}
