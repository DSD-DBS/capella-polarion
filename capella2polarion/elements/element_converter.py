# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Objects for serialization of capella objects to workitems."""

from __future__ import annotations

import enum
import logging
import pathlib
import re
import typing as t
from collections import abc as cabc

import capellambse
import markupsafe
import polarion_rest_api_client as polarion_api
from capellambse import model as m

from capella2polarion import data_model, polarion_html_helper
from capella2polarion.connectors import polarion_repo
from capella2polarion.elements import capella_object_renderer, data_session

DIAGRAM_WIDTH = 750

ADDITIONAL_DIAGRAM_WIDTH = 650

RE_CAMEL_CASE_2ND_WORD_PATTERN = re.compile(r"([a-z]+)([A-Z][a-z]+)")

logger = logging.getLogger(__name__)


def resolve_element_type(type_: str) -> str:
    """Return a valid Type ID for polarion for a given ``obj``."""
    return type_[0].lower() + type_[1:]


def _resolve_capella_attribute(
    converter_data: data_session.ConverterData, attribute: str
) -> polarion_api.TextContent | str:
    match attribute:
        case "layer":
            value = converter_data.layer
        case _:
            value = getattr(converter_data.capella_element, attribute)

    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, str):
        return value
    raise ValueError(f"Unsupported attribute type: {value!r}")


class CapellaWorkItemSerializer:
    """The general serializer class for CapellaWorkItems."""

    def __init__(
        self,
        model: capellambse.MelodyModel,
        capella_polarion_mapping: polarion_repo.PolarionDataRepository,
        converter_session: data_session.ConverterSession,
        generate_attachments: bool,
        generate_figure_captions: bool = False,
    ):
        self.capella_polarion_mapping = capella_polarion_mapping
        self.renderer = capella_object_renderer.CapellaObjectRenderer(
            model,
            generate_figure_captions,
            generate_attachments,
            capella_polarion_mapping,
        )
        self.converter_session = converter_session

    def serialize_all(self) -> list[data_model.CapellaWorkItem]:
        """Serialize all items of the converter_session."""
        return [
            item
            for uuid in self.converter_session
            if (item := self.serialize(uuid)) is not None
        ]

    def serialize(self, uuid: str) -> data_model.CapellaWorkItem | None:
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
                    data_model.CapellaWorkItem,
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

    # Serializer implementation starts below

    def __generic_work_item(
        self,
        converter_data: data_session.ConverterData,
        work_item_id: str | None,
    ) -> data_model.CapellaWorkItem:
        obj = converter_data.capella_element
        raw_description = getattr(obj, "description", None)
        uuids, value, attachments = self.renderer.sanitize_text(
            obj,
            raw_description or markupsafe.Markup(""),
            converter_data.errors,
        )
        converter_data.description_references = uuids
        requirement_types = self.renderer.get_requirement_types_text(
            obj, converter_data.errors
        )

        converter_data.work_item = data_model.CapellaWorkItem(
            id=work_item_id,
            type=converter_data.type_config.p_type,
            title=obj.name,
            uuid_capella=obj.uuid,
            description=polarion_api.HtmlContent(value),
            status="open",
            **requirement_types,  # type:ignore[arg-type]
        )
        assert converter_data.work_item is not None
        for attachment in attachments:
            polarion_html_helper.add_attachment_to_workitem(
                converter_data.work_item, attachment
            )

        return converter_data.work_item

    def _add_attributes(
        self,
        converter_data: data_session.ConverterData,
        attributes: list[dict[str, t.Any]],
    ) -> data_model.CapellaWorkItem:
        assert converter_data.work_item is not None
        for attribute in attributes:
            try:
                converter_data.work_item.additional_attributes[
                    attribute["polarion_id"]
                ] = _resolve_capella_attribute(
                    converter_data, attribute["capella_attr"]
                )
            except AttributeError:
                logger.error(
                    "Attribute %r not found on %r",
                    attribute["capella_attr"],
                    converter_data.type_config.p_type,
                )
                continue
            except ValueError as error:
                logger.error(error.args[0])

        return converter_data.work_item

    def _diagram(
        self,
        converter_data: data_session.ConverterData,
        render_params: dict[str, t.Any] | None = None,
    ) -> data_model.CapellaWorkItem:
        """Serialize a diagram for Polarion."""
        diagram = converter_data.capella_element
        assert converter_data.work_item is not None
        assert isinstance(diagram, m.Diagram)
        work_item_id = converter_data.work_item.id

        diagram_html, attachment = self.renderer.draw_diagram_svg(
            diagram,
            "diagram",
            "Diagram",
            DIAGRAM_WIDTH,
            "diagram",
            render_params,
        )

        converter_data.work_item = data_model.CapellaWorkItem(
            id=work_item_id,
            type=converter_data.type_config.p_type,
            title=diagram.name,
            uuid_capella=diagram.uuid,
            description=polarion_api.HtmlContent(diagram_html),
            status="open",
        )
        if attachment:
            polarion_html_helper.add_attachment_to_workitem(
                converter_data.work_item, attachment
            )

        return converter_data.work_item

    def _include_pre_and_post_condition(
        self, converter_data: data_session.ConverterData
    ) -> data_model.CapellaWorkItem:
        """Return generic attributes and pre- and post-condition."""
        obj = converter_data.capella_element
        assert hasattr(obj, "precondition"), "Missing PreCondition Attribute"
        assert hasattr(obj, "postcondition"), "Missing PostCondition Attribute"
        assert not isinstance(obj, m.Diagram)

        def get_condition(cap: m.ModelElement, name: str) -> str:
            if not (condition := getattr(cap, name)):
                return ""
            _, value, _ = self.renderer.sanitize_linked_text(
                condition, converter_data.errors
            )
            return f'<div style="text-align: center;">{value}</div>'

        pre_condition = get_condition(obj, "precondition")
        post_condition = get_condition(obj, "postcondition")

        assert converter_data.work_item, "No work item set yet"
        converter_data.work_item.preCondition = polarion_api.HtmlContent(
            pre_condition
        )
        converter_data.work_item.postCondition = polarion_api.HtmlContent(
            post_condition
        )
        return converter_data.work_item

    def _linked_text_as_description(
        self, converter_data: data_session.ConverterData
    ) -> data_model.CapellaWorkItem:
        """Return attributes for a ``Constraint``."""
        assert converter_data.work_item, "No work item set yet"
        assert converter_data.work_item.description, (
            "Description should already be defined"
        )
        (
            uuids,
            converter_data.work_item.description.value,
            attachments,
        ) = self.renderer.sanitize_linked_text(
            converter_data.capella_element, converter_data.errors
        )
        if uuids:
            converter_data.description_references = uuids

        converter_data.work_item.attachments += attachments
        return converter_data.work_item

    def _add_context_diagram(
        self,
        converter_data: data_session.ConverterData,
        render_params: dict[str, t.Any] | None = None,
        filters: list[str] | None = None,
    ) -> data_model.CapellaWorkItem:
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
    ) -> data_model.CapellaWorkItem:
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
        **fields: dict[str, str | pathlib.Path | dict[str, t.Any]],
    ) -> data_model.CapellaWorkItem:
        """Add a new custom field and fill it with rendered jinja content."""
        assert converter_data.work_item, "No work item set yet"
        for field_id, jinja_properties in fields.items():
            template_folder = jinja_properties.get("template_folder", "")
            assert isinstance(template_folder, str | pathlib.Path)
            template_path = jinja_properties["template_path"]
            assert isinstance(template_path, str | pathlib.Path)
            params = jinja_properties.get("render_parameters", {})
            assert isinstance(params, dict)
            # referenced UUIDs are ignored here as they are not in description
            _, value, attachments = self.renderer.render_jinja_template(
                template_folder,
                template_path,
                converter_data,
                params,
            )

            for attachment in attachments:
                polarion_html_helper.add_attachment_to_workitem(
                    converter_data.work_item, attachment
                )

            converter_data.work_item.additional_attributes[field_id] = (
                polarion_api.HtmlContent(value)
            )

        return converter_data.work_item

    def _jinja_as_description(
        self,
        converter_data: data_session.ConverterData,
        template_path: str,
        template_folder: str = "",
        render_parameters: dict[str, t.Any] | None = None,
    ) -> data_model.CapellaWorkItem:
        """Use a Jinja template to render the description content."""
        assert converter_data.work_item, "No work item set yet"
        assert converter_data.work_item.description, (
            "Description should already be defined"
        )

        uuids, value, attachments = self.renderer.render_jinja_template(
            template_folder,
            template_path,
            converter_data,
            render_parameters,
        )
        for attachment in attachments:
            polarion_html_helper.add_attachment_to_workitem(
                converter_data.work_item, attachment
            )

        converter_data.description_references = uuids
        converter_data.work_item.description.value = value
        return converter_data.work_item

    def _draw_additional_attributes_diagram(
        self,
        work_item: polarion_api.WorkItem,
        diagram: m.AbstractDiagram,
        attribute: str,
        title: str,
        render_params: dict[str, t.Any] | None = None,
    ) -> None:
        diagram_html, attachment = self.renderer.draw_diagram_svg(
            diagram,
            attribute,
            title,
            ADDITIONAL_DIAGRAM_WIDTH,
            "additional-attributes-diagram",
            render_params,
            f"{title} of {work_item.title}",
        )
        if attachment:
            polarion_html_helper.add_attachment_to_workitem(
                work_item, attachment
            )

        work_item.additional_attributes[attribute] = polarion_api.HtmlContent(
            diagram_html
        )
