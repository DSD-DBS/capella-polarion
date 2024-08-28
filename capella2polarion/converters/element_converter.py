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
import jinja2
import markupsafe
import polarion_rest_api_client as polarion_api
from capellambse import helpers as chelpers
from capellambse.model import common
from capellambse.model.crosslayer import interaction
from capellambse.model.layers import oa
from lxml import etree

from capella2polarion import data_models
from capella2polarion.connectors import polarion_repo
from capella2polarion.converters import data_session, polarion_html_helper

RE_DESCR_LINK_PATTERN = re.compile(
    r"<a href=\"hlink://([^\"]+)\">([^<]+)<\/a>"
)
RE_CAMEL_CASE_2ND_WORD_PATTERN = re.compile(r"([a-z]+)([A-Z][a-z]+)")

PrePostConditionElement = t.Union[
    oa.OperationalCapability, interaction.Scenario
]

logger = logging.getLogger(__name__)
C2P_IMAGE_PREFIX = "__C2P__"
JINJA_RENDERED_IMG_CLS = "jinja-rendered-image"


def resolve_element_type(type_: str) -> str:
    """Return a valid Type ID for polarion for a given ``obj``."""
    return type_[0].lower() + type_[1:]


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


def _condition(
    html: bool, value: str
) -> data_models.CapellaWorkItem.Condition:
    _type = "text/html" if html else "text/plain"
    return {
        "type": _type,
        "value": f'<div style="text-align: center;">{value}</div>',
    }


class CapellaWorkItemSerializer(polarion_html_helper.JinjaRendererMixin):
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
        self.jinja_envs: dict[str, jinja2.Environment] = {}

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
        assert converter_data.work_item is not None

        assert isinstance(converter_data.type_config.converters, dict)
        for converter, params in converter_data.type_config.converters.items():
            try:
                serializer: cabc.Callable[
                    ...,
                    data_models.CapellaWorkItem,
                ] = getattr(self, f"_{converter}")
                serializer(converter_data, **params)
            except Exception as error:
                converter_data.errors.add(
                    ", ".join([str(a) for a in error.args])
                )
                converter_data.work_item = None

        if converter_data.errors:
            log_args = (
                converter_data.capella_element._short_repr_(),
                "\n\t".join(converter_data.errors),
            )
            if converter_data.work_item is None:
                logger.error("Serialization of %r failed:\n\t%s", *log_args)
            else:
                logger.warning(
                    "Serialization of %r successful, but with warnings:\n\t%s",
                    *log_args,
                )
        return converter_data.work_item

    # General helper functions

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
        diagram: capellambse.model.diagram.AbstractDiagram,
        file_name: str,
        title: str,
        max_width: int,
        cls: str,
        render_params: dict[str, t.Any] | None = None,
    ) -> tuple[str, polarion_api.WorkItemAttachment | None]:
        file_name = f"{C2P_IMAGE_PREFIX}{file_name}.svg"

        if self.generate_attachments:
            try:
                render_params = render_params or {}
                diagram_svg = diagram.render("svg", **render_params)
            except Exception:
                logger.exception("Failed to render diagram %s", diagram.name)
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

        return (
            polarion_html_helper.generate_image_html(
                title, file_name, max_width, cls
            ),
            attachment,
        )

    def _render_jinja_template(
        self,
        template_folder: str | pathlib.Path,
        template_path: str | pathlib.Path,
        converter_data: data_session.ConverterData,
    ):
        env = self._get_jinja_env(str(template_folder))
        template = env.get_template(template_path)
        rendered_jinja = template.render(
            object=converter_data.capella_element,
            model=self.model,
            work_item=converter_data.work_item,
        )
        _, text, _ = self._sanitize_text(
            converter_data.capella_element, rendered_jinja
        )
        return text

    def setup_env(self, env: jinja2.Environment):
        """Add the link rendering filter."""
        env.filters["make_href"] = self.__make_href_filter
        env.globals["insert_diagram"] = self.__insert_diagram

    def __make_href_filter(self, obj: object) -> str | None:
        if (obj := self.check_model_element(obj)) is None:
            return "#"
        return f"hlink://{obj.uuid}"

    def __insert_diagram(
        self,
        work_item: data_models.CapellaWorkItem,
        diagram: capellambse.model.diagram.AbstractDiagram,
        file_name: str,
        render_params: dict[str, t.Any] | None = None,
        max_width: int = 800,
    ):
        if attachment := next(
            (
                att
                for att in work_item.attachments
                if att.file_name == f"{C2P_IMAGE_PREFIX}{file_name}.svg"
            ),
            None,
        ):
            return polarion_html_helper.generate_image_html(
                diagram.name,
                attachment.file_name,
                max_width,
                JINJA_RENDERED_IMG_CLS,
            )

        diagram_html, attachment = self._draw_diagram_svg(
            diagram,
            file_name,
            diagram.name,
            max_width,
            JINJA_RENDERED_IMG_CLS,
            render_params,
        )
        if attachment:
            self._add_attachment(work_item, attachment)

        return diagram_html

    def _draw_additional_attributes_diagram(
        self,
        work_item: data_models.CapellaWorkItem,
        diagram: capellambse.model.diagram.AbstractDiagram,
        attribute: str,
        title: str,
        render_params: dict[str, t.Any] | None = None,
    ):
        diagram_html, attachment = self._draw_diagram_svg(
            diagram,
            attribute,
            title,
            650,
            "additional-attributes-diagram",
            render_params,
        )
        if attachment:
            self._add_attachment(work_item, attachment)

        work_item.additional_attributes[attribute] = {
            "type": "text/html",
            "value": diagram_html,
        }

    def _sanitize_linked_text(
        self, obj: common.GenericElement
    ) -> tuple[
        list[str], markupsafe.Markup, list[polarion_api.WorkItemAttachment]
    ]:
        linked_text = getattr(
            obj, "specification", {"capella:linkedText": markupsafe.Markup("")}
        )["capella:linkedText"]
        linked_text = polarion_html_helper.RE_DESCR_DELETED_PATTERN.sub(
            lambda match: polarion_html_helper.strike_through(
                self._replace_markup(obj.uuid, match, [])
            ),
            linked_text,
        )
        linked_text = linked_text.replace("\n", "<br>")
        return self._sanitize_text(obj, linked_text)

    def _sanitize_text(
        self, obj: common.GenericElement, text: markupsafe.Markup | str
    ) -> tuple[
        list[str], markupsafe.Markup, list[polarion_api.WorkItemAttachment]
    ]:
        referenced_uuids: list[str] = []
        replaced_markup = RE_DESCR_LINK_PATTERN.sub(
            lambda match: self._replace_markup(
                obj.uuid, match, referenced_uuids, 2
            ),
            text,
        )

        attachments: list[polarion_api.WorkItemAttachment] = []

        def repair_images(node: etree._Element) -> None:
            if (
                node.tag != "img"
                or not self.generate_attachments
                or node.get("class") == JINJA_RENDERED_IMG_CLS
            ):
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
                self.converter_session[obj.uuid].errors.add(
                    f"Inline image can't be found from {file_path!r}."
                )

        repaired_markup = chelpers.process_html_fragments(
            replaced_markup, repair_images
        )
        return referenced_uuids, repaired_markup, attachments

    def _replace_markup(
        self,
        origin_uuid: str,
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
            self.converter_session[origin_uuid].errors.add(
                f"Non-existing model element referenced in description: {uuid}"
            )
            return polarion_html_helper.strike_through(
                match.group(default_group)
            )
        if pid := self.capella_polarion_mapping.get_work_item_id(uuid):
            referenced_uuids.append(uuid)
            return polarion_html_helper.POLARION_WORK_ITEM_URL.format(pid=pid)

        self.converter_session[origin_uuid].errors.add(
            f"Non-existing work item referenced in description: {uuid}"
        )
        return match.group(default_group)

    def _get_requirement_types_text(
        self,
        obj: common.GenericElement,
    ) -> dict[str, dict[str, str]]:
        type_texts = collections.defaultdict(list)
        for req in getattr(obj, "requirements", []):
            if req is None:
                self.converter_session[obj.uuid].errors.add(
                    "Found RequirementsRelation with broken target"
                )
                continue

            if not (req.type and req.text):
                identifier = (
                    req.long_name or req.name or req.summary or req.uuid
                )
                self.converter_session[obj.uuid].errors.add(
                    f"Found Requirement without text or type on {identifier!r}"
                )
                continue

            type_texts[req.type.long_name].append(req.text)
        return _format_texts(type_texts)

    # Serializer implementation starts below

    def __generic_work_item(
        self,
        converter_data: data_session.ConverterData,
        work_item_id: str | None,
    ) -> data_models.CapellaWorkItem:
        obj = converter_data.capella_element
        raw_description = getattr(obj, "description", None)
        uuids, value, attachments = self._sanitize_text(
            obj, raw_description or markupsafe.Markup("")
        )
        converter_data.description_references = uuids
        requirement_types = self._get_requirement_types_text(obj)

        converter_data.work_item = data_models.CapellaWorkItem(
            id=work_item_id,
            type=converter_data.type_config.p_type,
            title=obj.name,
            uuid_capella=obj.uuid,
            description_type="text/html",
            description=value,
            status="open",
            **requirement_types,
        )
        for attachment in attachments:
            self._add_attachment(converter_data.work_item, attachment)

        return converter_data.work_item

    def _diagram(
        self,
        converter_data: data_session.ConverterData,
        render_params: dict[str, t.Any] | None = None,
    ) -> data_models.CapellaWorkItem:
        """Serialize a diagram for Polarion."""
        diagram = converter_data.capella_element
        assert converter_data.work_item is not None
        work_item_id = converter_data.work_item.id

        diagram_html, attachment = self._draw_diagram_svg(
            diagram, "diagram", "Diagram", 750, "diagram", render_params
        )

        converter_data.work_item = data_models.CapellaWorkItem(
            id=work_item_id,
            type=converter_data.type_config.p_type,
            title=diagram.name,
            uuid_capella=diagram.uuid,
            description_type="text/html",
            description=diagram_html,
            status="open",
        )
        if attachment:
            self._add_attachment(converter_data.work_item, attachment)

        return converter_data.work_item

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
            _, value, _ = self._sanitize_linked_text(condition)
            return value

        pre_condition = get_condition(obj, "precondition")
        post_condition = get_condition(obj, "postcondition")

        assert converter_data.work_item, "No work item set yet"
        converter_data.work_item.preCondition = _condition(True, pre_condition)
        converter_data.work_item.postCondition = _condition(
            True, post_condition
        )
        return converter_data.work_item

    def _linked_text_as_description(
        self, converter_data: data_session.ConverterData
    ) -> data_models.CapellaWorkItem:
        """Return attributes for a ``Constraint``."""
        assert converter_data.work_item, "No work item set yet"
        (
            uuids,
            converter_data.work_item.description,
            attachments,
        ) = self._sanitize_linked_text(converter_data.capella_element)
        if uuids:
            converter_data.description_references = uuids

        converter_data.work_item.attachments += attachments
        return converter_data.work_item

    def _add_context_diagram(
        self,
        converter_data: data_session.ConverterData,
        render_params: dict[str, t.Any] | None = None,
        filters: list[str] | None = None,
    ) -> data_models.CapellaWorkItem:
        """Add a new custom field context diagram."""
        assert converter_data.work_item, "No work item set yet"
        diagram = converter_data.capella_element.context_diagram
        for filter in filters or []:
            diagram.filters.add(filter)

        self._draw_additional_attributes_diagram(
            converter_data.work_item,
            diagram,
            "context_diagram",
            "Context Diagram",
            render_params,
        )

        return converter_data.work_item

    def _add_tree_diagram(
        self,
        converter_data: data_session.ConverterData,
        render_params: dict[str, t.Any] | None = None,
        filters: list[str] | None = None,
    ) -> data_models.CapellaWorkItem:
        """Add a new custom field tree diagram."""
        assert converter_data.work_item, "No work item set yet"
        diagram = converter_data.capella_element.tree_view
        for filter in filters or []:
            diagram.filters.add(filter)

        self._draw_additional_attributes_diagram(
            converter_data.work_item,
            diagram,
            "tree_view",
            "Tree View",
            render_params,
        )

        return converter_data.work_item

    def _add_jinja_fields(
        self,
        converter_data: data_session.ConverterData,
        fields: dict[str, dict[str, str]],
    ) -> data_models.CapellaWorkItem:
        """Add a new custom field and fill it with rendered jinja content."""
        assert converter_data.work_item, "No work item set yet"
        for field, jinja_properties in fields.items():
            converter_data.work_item.additional_attributes[field] = {
                "type": "text/html",
                "value": self._render_jinja_template(
                    jinja_properties.get("template_folder", ""),
                    jinja_properties["template_path"],
                    converter_data,
                ),
            }

        return converter_data.work_item

    def _jinja_as_description(
        self,
        converter_data: data_session.ConverterData,
        template_path: str,
        template_folder: str = "",
    ) -> data_models.CapellaWorkItem:
        """Use a Jinja template to render the description content."""
        assert converter_data.work_item, "No work item set yet"
        converter_data.work_item.description = self._render_jinja_template(
            template_folder, template_path, converter_data
        )
        return converter_data.work_item
