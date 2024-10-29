# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module providing the CapellaWorkItemAttachment classes."""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import logging
import typing as t

import cairosvg
import polarion_rest_api_client as polarion_api
from capellambse import model
from capellambse_context_diagrams import context

SVG_MIME_TYPE = "image/svg+xml"
PNG_MIME_TYPE = "image/png"
logger = logging.getLogger(__name__)


__all__ = [
    "calculate_content_checksum",
    "Capella2PolarionAttachment",
    "CapellaDiagramAttachment",
    "CapellaContextDiagramAttachment",
    "PngConvertedSvgAttachment",
]


def calculate_content_checksum(
    attachment: polarion_api.WorkItemAttachment,
) -> str:
    """Calculate content checksum for an attachment."""
    return base64.b64encode(attachment.content_bytes or b"").decode("utf8")


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
        try:
            diagram_svg = self.diagram.render("svg", **self.render_params)
        except Exception as e:
            logger.error(
                "Failed to render diagram %s", self.diagram.name, exc_info=e
            )
            diagram_svg = self.diagram.as_svg
        if isinstance(diagram_svg, str):
            diagram_svg = diagram_svg.encode("utf8")
        self._content_bytes = diagram_svg
        return diagram_svg

    @content_bytes.setter
    def content_bytes(self, value: bytes | None):
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
                    input_str = ";".join(eit.json() for eit in elk_input)
                else:
                    input_str = elk_input.json()
                self._checksum = hashlib.sha256(
                    input_str.encode("utf-8")
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


class PngConvertedSvgAttachment(Capella2PolarionAttachment):
    """A special attachment type for PNGs which shall be created from SVGs.

    An SVG attachment must be provided to create this attachment. The
    actual conversion of SVG to PNG takes place when content bytes are
    requested. For that reason creating this attachment does not trigger
    diagram rendering as long as context_bytes aren't requested.
    """

    def __init__(self, attachment: polarion_api.WorkItemAttachment):
        assert (
            attachment.mime_type == SVG_MIME_TYPE
        ), "PngConvertedSvgAttachment must be initialized using SVG attachment"
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
    def content_bytes(self, value: bytes | None):
        self._content_bytes = value
