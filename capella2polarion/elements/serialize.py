# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Objects for serialization of capella objects to workitems."""
from __future__ import annotations

import base64 as b64
import collections.abc as cabc
import logging
import mimetypes
import pathlib
import re
import typing as t

import cairosvg
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
    content = diagram_path.read_bytes()
    content_svg = b64.standard_b64encode(content)
    svg_attachment = attachment("image/svg+xml", f"{diag.uuid}", content_svg)
    content_png = b64.b16encode(cairosvg.svg2png(content.decode("utf8")))
    png_attachment = attachment("image/png", f"{diag.uuid}", content_png)
    return CapellaWorkItem(
        type="diagram",
        title=diag.name,
        status="open",
        attachments=[svg_attachment, png_attachment],
        uuid_capella=diag.uuid,
    )


def attachment(
    mime_type: str, name: str, content: bytes
) -> polarion_api.WorkItemAttachment:
    """Serialize an attachment for Polarion."""
    return polarion_api.WorkItemAttachment(
        work_item_id="",
        id="",
        content_bytes=content,
        mime_type=mime_type,
        file_name=name,
    )


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
    return CapellaWorkItem(
        type=helpers.resolve_element_type(xtype),
        title=obj.name,
        description_type="text/html",
        description=value,
        status="open",
        uuid_capella=obj.uuid,
    )


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
                b64_img = b64.b64encode(img.read()).decode("utf8")
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
    else:
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


SERIALIZERS = {
    "CapabilityRealization": include_pre_and_post_condition,
    "LogicalComponent": component_or_actor,
    "OperationalCapability": include_pre_and_post_condition,
    "PhysicalComponent": physical_component,
    "SystemComponent": component_or_actor,
    "Scenario": include_pre_and_post_condition,
    "Constraint": constraint,
}
