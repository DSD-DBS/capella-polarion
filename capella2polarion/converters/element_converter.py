# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Objects for serialization of capella objects to workitems."""
from __future__ import annotations

import collections
import hashlib
import logging
import mimetypes
import pathlib
import re
import typing as t
from collections import abc as cabc

import cairosvg
import capellambse
import markupsafe
import polarion_rest_api_client as polarion_api
from capellambse import helpers as chelpers
from capellambse.model import common
from capellambse.model.crosslayer import interaction
from capellambse.model.layers import oa
from lxml import etree

from capella2polarion import data_models
from capella2polarion.connectors import polarion_repo
from capella2polarion.converters import data_session

RE_DESCR_LINK_PATTERN = re.compile(
    r"<a href=\"hlink://([^\"]+)\">([^<]+)<\/a>"
)
RE_DESCR_DELETED_PATTERN = re.compile(
    f"<deleted element ({chelpers.RE_VALID_UUID.pattern})>"
)
RE_CAMEL_CASE_2ND_WORD_PATTERN = re.compile(r"([a-z]+)([A-Z][a-z]+)")
DIAGRAM_STYLES = {"max-width": "100%"}
POLARION_WORK_ITEM_URL = (
    '<span class="polarion-rte-link" data-type="workItem" '
    'id="fake" data-item-id="{pid}" data-option-id="long">'
    "</span>"
)

PrePostConditionElement = t.Union[
    oa.OperationalCapability, interaction.Scenario
]

logger = logging.getLogger(__name__)
C2P_IMAGE_PREFIX = "__C2P__"


def resolve_element_type(type_: str) -> str:
    """Return a valid Type ID for polarion for a given ``obj``."""
    return type_[0].lower() + type_[1:]


def strike_through(string: str) -> str:
    """Return a striked-through html span from given ``string``."""
    if match := RE_DESCR_DELETED_PATTERN.match(string):
        string = match.group(1)
    return f'<span style="text-decoration: line-through;">{string}</span>'


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


def _get_requirement_types_text(
    obj: common.GenericElement,
) -> dict[str, dict[str, str]]:
    type_texts = collections.defaultdict(list)
    for req in getattr(obj, "requirements", []):
        if req is None:
            logger.error(
                "RequirementsRelation with broken target found %r", obj.name
            )
            continue

        if not (req.type and req.text):
            identifier = req.long_name or req.name or req.summary or req.uuid
            logger.warning(
                "Requirement without text or type found %r", identifier
            )
            continue

        type_texts[req.type.long_name].append(req.text)
    return _format_texts(type_texts)


def _condition(
    html: bool, value: str
) -> data_models.CapellaWorkItem.Condition:
    _type = "text/html" if html else "text/plain"
    return {"type": _type, "value": value}


def _generate_image_html(
    title: str, attachment_id: str, max_width: int
) -> str:
    """Generate an image as HTMl with the given source."""
    description = (
        f'<span><img title="{title}" '
        f'src="workitemimg:{attachment_id}" '
        f'style="max-width: {max_width}px;"/></span>'
    )
    return description


class CapellaWorkItemSerializer:
    """The general serializer class for CapellaWorkItems."""

    diagram_cache_path: pathlib.Path
    model: capellambse.MelodyModel

    def __init__(
        self,
        model: capellambse.MelodyModel,
        capella_polarion_mapping: polarion_repo.PolarionDataRepository,
        converter_session: data_session.ConverterSession,
        generate_attachments: bool,
    ):
        self.model = model
        self.capella_polarion_mapping = capella_polarion_mapping
        self.converter_session = converter_session
        self.generate_attachments = generate_attachments

    def serialize_all(self) -> list[data_models.CapellaWorkItem]:
        """Serialize all items of the converter_session."""
        work_items = [self.serialize(uuid) for uuid in self.converter_session]
        return list(filter(None, work_items))

    def serialize(self, uuid: str) -> data_models.CapellaWorkItem | None:
        """Return a CapellaWorkItem for the given diagram or element."""
        converter_data = self.converter_session[uuid]
        work_item_id = None
        if old := self.capella_polarion_mapping.get_work_item_by_capella_uuid(
            uuid
        ):
            work_item_id = old.id
        self.__generic_work_item(converter_data, work_item_id)

        for converter in converter_data.type_config.converters or []:
            try:
                serializer: cabc.Callable[
                    [data_session.ConverterData], data_models.CapellaWorkItem
                ] = getattr(self, f"_{converter}")
                serializer(converter_data)
            except Exception as error:
                logger.error(
                    "Serializing model element failed. %s", error.args[0]
                )
                converter_data.work_item = None
                return None  # Force to not overwrite on failure
        assert converter_data.work_item is not None

        return converter_data.work_item

    def _add_attachment(
        self,
        work_item: data_models.CapellaWorkItem,
        attachment: polarion_api.WorkItemAttachment,
    ):
        attachment.work_item_id = work_item.id or ""
        work_item.attachments.append(attachment)
        if attachment.mime_type == "image/svg+xml":
            work_item.attachments.append(
                polarion_api.WorkItemAttachment(
                    attachment.work_item_id,
                    "",
                    attachment.title,
                    cairosvg.svg2png(attachment.content_bytes),
                    "image/png",
                    attachment.file_name[:-3] + "png",
                )
            )

    def _draw_diagram_svg(
        self,
        diagram: capellambse.model.diagram.Diagram,
        file_name: str,
        title: str,
        max_width: int,
    ) -> tuple[str, polarion_api.WorkItemAttachment | None]:
        file_name = f"{C2P_IMAGE_PREFIX}{file_name}.svg"

        if self.generate_attachments:
            try:
                diagram_svg = diagram.render("svg")
            except Exception as error:
                logger.exception(
                    "Failed to get diagram from cache. Error: %s", error
                )
                diagram_svg = diagram.as_svg

            if isinstance(diagram_svg, str):
                diagram_svg = diagram_svg.encode("utf8")

            attachment = polarion_api.WorkItemAttachment(
                "",
                "",
                title,
                diagram_svg,
                "image/svg+xml",
                file_name,
            )
        else:
            attachment = None

        return _generate_image_html(title, file_name, max_width), attachment

    def _draw_additional_attributes_diagram(
        self,
        work_item: data_models.CapellaWorkItem,
        diagram: capellambse.model.diagram.Diagram,
        attribute: str,
        title: str,
    ):
        diagram_html, attachment = self._draw_diagram_svg(
            diagram, attribute, title, 650
        )
        if attachment:
            self._add_attachment(work_item, attachment)
        work_item.additional_attributes[attribute] = {
            "type": "text/html",
            "value": diagram_html,
        }

    def _diagram(
        self, converter_data: data_session.ConverterData
    ) -> data_models.CapellaWorkItem:
        """Serialize a diagram for Polarion."""
        diagram = converter_data.capella_element
        assert converter_data.work_item is not None
        work_item_id = converter_data.work_item.id

        diagram_html, attachment = self._draw_diagram_svg(
            diagram, "diagram", "Diagram", 800
        )

        converter_data.work_item = data_models.CapellaWorkItem(
            id=work_item_id,
            type=converter_data.type_config.p_type,
            title=diagram.name,
            description_type="text/html",
            description=diagram_html,
            status="open",
            uuid_capella=diagram.uuid,
        )
        if attachment:
            self._add_attachment(converter_data.work_item, attachment)
        return converter_data.work_item

    def __generic_work_item(
        self, converter_data: data_session.ConverterData, work_item_id
    ) -> data_models.CapellaWorkItem:
        obj = converter_data.capella_element
        raw_description = getattr(obj, "description", None)
        uuids, value, attachments = self._sanitize_description(
            obj, raw_description or markupsafe.Markup("")
        )
        converter_data.description_references = uuids
        requirement_types = _get_requirement_types_text(obj)
        converter_data.work_item = data_models.CapellaWorkItem(
            id=work_item_id,
            type=converter_data.type_config.p_type,
            title=obj.name,
            description_type="text/html",
            description=value,
            status="open",
            uuid_capella=obj.uuid,
            **requirement_types,
        )
        for attachment in attachments:
            self._add_attachment(converter_data.work_item, attachment)

        return converter_data.work_item

    def _sanitize_description(
        self, obj: common.GenericElement, descr: markupsafe.Markup
    ) -> tuple[
        list[str], markupsafe.Markup, list[polarion_api.WorkItemAttachment]
    ]:
        referenced_uuids: list[str] = []
        replaced_markup = RE_DESCR_LINK_PATTERN.sub(
            lambda match: self._replace_markup(match, referenced_uuids, 2),
            descr,
        )

        attachments: list[polarion_api.WorkItemAttachment] = []

        def repair_images(node: etree._Element) -> None:
            if node.tag != "img" or not self.generate_attachments:
                return

            file_url = pathlib.PurePosixPath(node.get("src"))
            workspace = file_url.parts[0]
            file_path = pathlib.PurePosixPath(*file_url.parts[1:])
            mime_type, _ = mimetypes.guess_type(file_url)
            resources = self.model.resources
            filehandler = resources[
                ["\x00", workspace][workspace in resources]
            ]
            try:
                with filehandler.open(file_path, "r") as img:
                    content = img.read()
                    file_name = hashlib.md5(
                        str(file_path).encode("utf8")
                    ).hexdigest()
                    attachments.append(
                        polarion_api.WorkItemAttachment(
                            "",
                            "",
                            file_path.name,
                            content,
                            mime_type,
                            f"{file_name}.{file_path.suffix}",
                        )
                    )
                    node.attrib["src"] = f"workitemimg:{file_name}"

            except FileNotFoundError:
                logger.error(
                    "Inline image can't be found from %r for %r",
                    file_path,
                    obj._short_repr_(),
                )

        repaired_markup = chelpers.process_html_fragments(
            replaced_markup, repair_images
        )
        return referenced_uuids, repaired_markup, attachments

    def _replace_markup(
        self,
        match: re.Match,
        referenced_uuids: list[str],
        default_group: int = 1,
    ) -> str:
        """Replace UUID references in a ``match`` with a work item link.

        If the UUID doesn't correspond to an existing work item the
        original text is returned.
        """
        uuid = match.group(1)
        try:
            self.model.by_uuid(uuid)
        except KeyError:
            logger.error("Found link to non-existing model element: %r", uuid)
            return strike_through(match.group(default_group))
        if pid := self.capella_polarion_mapping.get_work_item_id(uuid):
            referenced_uuids.append(uuid)
            return POLARION_WORK_ITEM_URL.format(pid=pid)
        logger.warning("Found reference to non-existing work item: %r", uuid)
        return match.group(default_group)

    def _include_pre_and_post_condition(
        self, converter_data: data_session.ConverterData
    ) -> data_models.CapellaWorkItem:
        """Return generic attributes and pre- and post-condition."""
        obj = converter_data.capella_element
        assert hasattr(obj, "precondition"), "Missing PreCondition Attribute"
        assert hasattr(obj, "postcondition"), "Missing PostCondition Attribute"

        def get_condition(cap: PrePostConditionElement, name: str) -> str:
            if not (condition := getattr(cap, name)):
                return ""
            return condition.specification["capella:linkedText"].striptags()

        def matcher(match: re.Match) -> str:
            return strike_through(self._replace_markup(match, []))

        pre_condition = RE_DESCR_DELETED_PATTERN.sub(
            matcher, get_condition(obj, "precondition")
        )
        post_condition = RE_DESCR_DELETED_PATTERN.sub(
            matcher, get_condition(obj, "postcondition")
        )

        assert converter_data.work_item, "No work item set yet"
        converter_data.work_item.preCondition = _condition(True, pre_condition)
        converter_data.work_item.postCondition = _condition(
            True, post_condition
        )
        return converter_data.work_item

    def _get_linked_text(
        self, converter_data: data_session.ConverterData
    ) -> tuple[markupsafe.Markup, list[polarion_api.WorkItemAttachment]]:
        """Return sanitized markup of the given ``obj`` linked text."""
        obj = converter_data.capella_element
        default = {"capella:linkedText": markupsafe.Markup("")}
        description = getattr(obj, "specification", default)[
            "capella:linkedText"
        ].striptags()
        uuids, value, attachments = self._sanitize_description(
            obj, description
        )
        if uuids:
            converter_data.description_references = uuids
        return value, attachments

    def _linked_text_as_description(
        self, converter_data: data_session.ConverterData
    ) -> data_models.CapellaWorkItem:
        """Return attributes for a ``Constraint``."""
        # pylint: disable-next=attribute-defined-outside-init
        assert converter_data.work_item, "No work item set yet"
        (
            converter_data.work_item.description,
            attachments,
        ) = self._get_linked_text(converter_data)
        converter_data.work_item.attachments += attachments
        return converter_data.work_item

    def _add_context_diagram(
        self, converter_data: data_session.ConverterData
    ) -> data_models.CapellaWorkItem:
        """Add a new custom field context diagram."""
        assert converter_data.work_item, "No work item set yet"
        diagram = converter_data.capella_element.context_diagram

        self._draw_additional_attributes_diagram(
            converter_data.work_item,
            diagram,
            "context_diagram",
            "Context Diagram",
        )

        return converter_data.work_item

    def _add_tree_diagram(
        self, converter_data: data_session.ConverterData
    ) -> data_models.CapellaWorkItem:
        """Add a new custom field tree diagram."""
        assert converter_data.work_item, "No work item set yet"
        diagram = converter_data.capella_element.tree_view

        self._draw_additional_attributes_diagram(
            converter_data.work_item, diagram, "tree_view", "Tree View"
        )

        return converter_data.work_item
