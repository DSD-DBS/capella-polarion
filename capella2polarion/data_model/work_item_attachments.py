# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module providing the CapellaWorkItemAttachment classes."""

from __future__ import annotations

import base64
import dataclasses
import hashlib
import json
import logging
import typing as t

import cairosvg
import polarion_rest_api_client as polarion_api
from capellambse import model
from capellambse_context_diagrams import context

from capella2polarion import errors

SVG_MIME_TYPE = "image/svg+xml"
PNG_MIME_TYPE = "image/png"
logger = logging.getLogger(__name__)


__all__ = [
    "Capella2PolarionAttachment",
    "CapellaContextDiagramAttachment",
    "CapellaDiagramAttachment",
    "PngConvertedSvgAttachment",
    "calculate_content_checksum",
]


def calculate_content_checksum(
    attachment: polarion_api.WorkItemAttachment,
) -> str:
    """Calculate content checksum for an attachment."""
    try:
        return base64.b64encode(attachment.content_bytes or b"").decode("utf8")
    except Exception as e:
        logger.error(
            "Failed to read content bytes for attachment %s of WorkItem %s.",
            attachment.file_name,
            attachment.work_item_id,
            exc_info=e,
        )
        return errors.RENDER_ERROR_CHECKSUM


@dataclasses.dataclass
class Capella2PolarionAttachment(polarion_api.WorkItemAttachment):
    """Stub Base-Class for Capella2Polarion attachments."""

    _checksum: str | None = None

    @property
    def content_checksum(self) -> str:
        """Calculate the checksum for the content of the attachment."""
        if self._checksum is None:
            self._checksum = calculate_content_checksum(self)
        return self._checksum


class CapellaDiagramAttachment(Capella2PolarionAttachment):
    """A class for lazy loading content_bytes for diagram attachments."""

    def __init__(
        self,
        diagram: model.AbstractDiagram,
        file_name: str,
        render_params: dict[str, t.Any] | None,
        title: str,
    ):
        super().__init__(
            "",
            "",
            title,
            None,
            SVG_MIME_TYPE,
            file_name,
        )
        self.render_params = render_params or {}
        self.diagram = diagram
        self._content_bytes: bytes | None = None

    @property
    def content_bytes(self) -> bytes | None:
        """Diagrams are only rendered, if content_bytes are requested."""
        if self._content_bytes:
            return self._content_bytes
        diagram_svg = self.diagram.render("svg", **self.render_params)
        if isinstance(diagram_svg, str):
            diagram_svg = diagram_svg.encode("utf8")
        self._content_bytes = diagram_svg
        return diagram_svg

    @content_bytes.setter
    def content_bytes(self, value: bytes | None) -> None:
        self._content_bytes = value


class CapellaContextDiagramAttachment(CapellaDiagramAttachment):
    """A dedicated attachment type for Capella context diagrams.

    Implements a checksum property using the elk input instead of
    content. This will speed up the checksum calculation a lot.
    """

    def __init__(
        self,
        diagram: context.ContextDiagram,
        file_name: str,
        render_params: dict[str, t.Any] | None,
        title: str,
    ):
        super().__init__(diagram, file_name, render_params, title)

    @property
    def content_checksum(self) -> str:
        """Return checksum based on elk input for ContextDiagrams else None."""
        if self._checksum is None:
            try:
                elk_input = self.diagram.elk_input_data(self.render_params)
                if isinstance(elk_input, tuple):
                    input_data, edges_or_list = elk_input
                    if isinstance(edges_or_list, list):
                        input_str = (
                            input_data.model_dump_json(exclude_defaults=True)
                            + ";"
                            + ";".join(
                                edge.model_dump_json(exclude_defaults=True)
                                for edge in edges_or_list
                            )
                        )
                    else:
                        input_str = ";".join(
                            obj.model_dump_json(exclude_defaults=True)
                            for obj in elk_input
                        )
                else:
                    input_str = elk_input.model_dump_json(
                        exclude_defaults=True
                    )

                styleclass_map = self._build_styleclass_map(elk_input)
                styleclass_str = json.dumps(
                    styleclass_map, sort_keys=True, separators=(",", ":")
                )
                self._checksum = hashlib.sha256(
                    f"{input_str};{styleclass_str}".encode()
                ).hexdigest()
            except Exception as e:
                logger.error(
                    "Failed to get elk_input for attachment %s of WorkItem %s."
                    " Using content checksum instead.",
                    self.file_name,
                    self.work_item_id,
                    exc_info=e,
                )
                return super().content_checksum
        return self._checksum

    def _build_styleclass_map(self, elk_input: t.Any) -> dict[str, str]:
        """Build a mapping of all UUIDs to their styleclasses.

        Only includes ports, children (elements), and edges. Labels are
        excluded as they inherit styleclasses from their parents.
        """
        styleclass_map: dict[str, str] = {}
        if isinstance(elk_input, tuple):
            input_data = elk_input[0]
            if len(elk_input) > 1:
                edges_or_list = elk_input[1]
                if isinstance(edges_or_list, list):
                    for edge in edges_or_list:
                        if (
                            hasattr(edge, "id")
                            and edge.id
                            and (styleclass := self._get_styleclass(edge.id))
                        ):
                            styleclass_map[edge.id] = styleclass
                else:
                    self._extract_uuids_recursive(
                        edges_or_list, styleclass_map
                    )
        else:
            input_data = elk_input

        self._extract_uuids_recursive(input_data, styleclass_map)
        return styleclass_map

    def _extract_uuids_recursive(
        self, elk_data: t.Any, styleclass_map: dict[str, str]
    ) -> None:
        if hasattr(elk_data, "id") and elk_data.id:
            styleclass = self._get_styleclass(elk_data.id)
            if styleclass:
                styleclass_map[elk_data.id] = styleclass

        if hasattr(elk_data, "children"):
            for child in elk_data.children:
                self._extract_uuids_recursive(child, styleclass_map)

        if hasattr(elk_data, "ports"):
            for port in elk_data.ports:
                if hasattr(port, "id") and port.id:
                    styleclass = self._get_styleclass(port.id)
                    if styleclass:
                        styleclass_map[port.id] = styleclass

        if hasattr(elk_data, "edges"):
            for edge in elk_data.edges:
                if hasattr(edge, "id") and edge.id:
                    styleclass = self._get_styleclass(edge.id)
                    if styleclass:
                        styleclass_map[edge.id] = styleclass

    def _get_styleclass(self, uuid: str) -> str | None:
        """Return the style-class string from a given UUID.

        This mirrors the logic from the context diagram serializer's
        get_styleclass method.
        """
        try:
            melodyobj = self.diagram._model.by_uuid(uuid)
        except (KeyError, ValueError):
            # capellambse raises ValueError ("Malformed link") for
            # synthetic IDs such as "__Derived-ComponentExchange:<uuid>"
            if not uuid.startswith("__"):
                return None
            return uuid[2:].split(":", 1)[0]
        else:
            if isinstance(melodyobj, model.Diagram):
                return melodyobj.type.value
            return melodyobj._get_styleclass()


class PngConvertedSvgAttachment(Capella2PolarionAttachment):
    """A special attachment type for PNGs which shall be created from SVGs.

    An SVG attachment must be provided to create this attachment. The
    actual conversion of SVG to PNG takes place when content bytes are
    requested. For that reason creating this attachment does not trigger
    diagram rendering as long as context_bytes aren't requested.
    """

    def __init__(self, attachment: polarion_api.WorkItemAttachment):
        assert attachment.mime_type == SVG_MIME_TYPE, (
            "PngConvertedSvgAttachment must be initialized using SVG attachment"
        )
        assert attachment.file_name is not None, "The file_name must be filled"
        super().__init__(
            attachment.work_item_id,
            "",
            attachment.title,
            None,
            PNG_MIME_TYPE,
            f"{attachment.file_name[:-3]}png",
        )
        self._content_bytes: bytes | None = None
        self._svg_attachment = attachment

    @property
    def content_bytes(self) -> bytes | None:
        """The content bytes are created from the SVG when requested."""
        if not self._content_bytes:
            self._content_bytes = cairosvg.svg2png(
                self._svg_attachment.content_bytes
            )
        return self._content_bytes

    @content_bytes.setter
    def content_bytes(self, value: bytes | None) -> None:
        self._content_bytes = value
