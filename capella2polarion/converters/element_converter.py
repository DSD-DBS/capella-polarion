# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Objects for serialization of capella objects to workitems."""
from __future__ import annotations

import base64
import collections
import logging
import mimetypes
import pathlib
import re
import typing as t
from collections import abc as cabc

import capellambse
import markupsafe
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


def resolve_element_type(type_: str) -> str:
    """Return a valid Type ID for polarion for a given ``obj``."""
    return type_[0].lower() + type_[1:]


def strike_through(string: str) -> str:
    """Return a striked-through html span from given ``string``."""
    if match := RE_DESCR_DELETED_PATTERN.match(string):
        string = match.group(1)
    return f'<span style="text-decoration: line-through;">{string}</span>'


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
    for req in obj.requirements:
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


def _generate_image_html(src: str) -> str:
    """Generate an image as HTMl with the given source."""
    style = "; ".join(
        (f"{key}: {value}" for key, value in DIAGRAM_STYLES.items())
    )
    description = f'<html><p><img style="{style}" src="{src}" /></p></html>'
    return description


class CapellaWorkItemSerializer:
    """The general serializer class for CapellaWorkItems."""

    diagram_cache_path: pathlib.Path
    model: capellambse.MelodyModel

    def __init__(
        self,
        diagram_cache_path: pathlib.Path,
        model: capellambse.MelodyModel,
        capella_polarion_mapping: polarion_repo.PolarionDataRepository,
        converter_session: data_session.ConverterSession,
    ):
        self.diagram_cache_path = diagram_cache_path
        self.model = model
        self.capella_polarion_mapping = capella_polarion_mapping
        self.converter_session = converter_session

    def serialize_all(self):
        """Serialize all items of the converter_session."""
        work_items = [self.serialize(uuid) for uuid in self.converter_session]
        return list(filter(None, work_items))

    def serialize(
        self,
        uuid: str,
    ) -> data_models.CapellaWorkItem | None:
        """Return a CapellaWorkItem for the given diagram or element."""
        converter_data = self.converter_session[uuid]
        try:
            serializer: cabc.Callable[
                [data_session.ConverterData], data_models.CapellaWorkItem
            ] = getattr(
                self,
                f"_{converter_data.type_config.converter}",
                self._generic_work_item,
            )
            converter_data.work_item = serializer(converter_data)
            if old := self.capella_polarion_mapping.get_work_item_by_capella_uuid(
                converter_data.work_item.uuid_capella
            ):
                converter_data.work_item.id = old.id

            return converter_data.work_item
        except Exception as error:
            logger.error("Serializing model element failed. %s", error.args[0])
            return None

    def _diagram(
        self, converter_data: data_session.ConverterData
    ) -> data_models.CapellaWorkItem:
        """Serialize a diagram for Polarion."""
        diag = converter_data.capella_element
        diagram_path = self.diagram_cache_path / f"{diag.uuid}.svg"
        src = _decode_diagram(diagram_path)
        description = _generate_image_html(src)
        return data_models.CapellaWorkItem(
            type=converter_data.type_config.p_type,
            title=diag.name,
            description_type="text/html",
            description=description,
            status="open",
            uuid_capella=diag.uuid,
        )

    def _generic_work_item(
        self, converter_data: data_session.ConverterData
    ) -> data_models.CapellaWorkItem:
        obj = converter_data.capella_element
        raw_description = getattr(obj, "description", markupsafe.Markup(""))
        uuids, value = self._sanitize_description(obj, raw_description)
        converter_data.description_references = uuids
        requirement_types = _get_requirement_types_text(obj)
        return data_models.CapellaWorkItem(
            type=converter_data.type_config.p_type,
            title=obj.name,
            description_type="text/html",
            description=value,
            status="open",
            uuid_capella=obj.uuid,
            **requirement_types,
        )

    def _sanitize_description(
        self, obj: common.GenericElement, descr: markupsafe.Markup
    ) -> tuple[list[str], markupsafe.Markup]:
        referenced_uuids: list[str] = []
        replaced_markup = RE_DESCR_LINK_PATTERN.sub(
            lambda match: self._replace_markup(match, referenced_uuids, 2),
            descr,
        )

        def repair_images(node: etree._Element) -> None:
            if node.tag != "img":
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
                    b64_img = base64.b64encode(img.read()).decode("utf8")
                    node.attrib["src"] = f"data:{mime_type};base64,{b64_img}"
            except FileNotFoundError:
                logger.error(
                    "Inline image can't be found from %r for %r",
                    file_path,
                    obj._short_repr_(),
                )

        repaired_markup = chelpers.process_html_fragments(
            replaced_markup, repair_images
        )
        return referenced_uuids, repaired_markup

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

        work_item = self._generic_work_item(converter_data)
        pre_condition = RE_DESCR_DELETED_PATTERN.sub(
            matcher, get_condition(obj, "precondition")
        )
        post_condition = RE_DESCR_DELETED_PATTERN.sub(
            matcher, get_condition(obj, "postcondition")
        )

        work_item.preCondition = _condition(True, pre_condition)
        work_item.postCondition = _condition(True, post_condition)

        return work_item

    def _get_linked_text(
        self, converter_data: data_session.ConverterData
    ) -> markupsafe.Markup:
        """Return sanitized markup of the given ``obj`` linked text."""
        obj = converter_data.capella_element
        description = obj.specification["capella:linkedText"].striptags()
        uuids, value = self._sanitize_description(obj, description)
        if uuids:
            converter_data.description_references = uuids
        return value

    def _linked_text_as_description(
        self, converter_data: data_session.ConverterData
    ) -> data_models.CapellaWorkItem:
        """Return attributes for a ``Constraint``."""
        work_item = self._generic_work_item(converter_data)
        # pylint: disable-next=attribute-defined-outside-init
        work_item.description = self._get_linked_text(converter_data)
        return work_item

    def _add_context_diagram(
        self, converter_data: data_session.ConverterData
    ) -> data_models.CapellaWorkItem:
        """Add a new custom field context diagram."""
        work_item = self._generic_work_item(converter_data)
        diagram = converter_data.capella_element.context_diagram
        work_item.additional_attributes["context_diagram"] = {
            "type": "text/html",
            "value": _generate_image_html(diagram.as_datauri_svg),
        }
        return work_item
