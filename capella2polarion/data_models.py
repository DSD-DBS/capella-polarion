# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module providing the CapellaWorkItem class."""
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

from capella2polarion.converters import text_work_item_provider

WORK_ITEM_CHECKSUM_KEY = "__C2P__WORK_ITEM"
SVG_MIME_TYPE = "image/svg+xml"
PNG_MIME_TYPE = "image/png"
logger = logging.getLogger(__name__)


def _calculate_content_checksum(
    attachment: polarion_api.WorkItemAttachment,
) -> str:
    return base64.b64encode(attachment.content_bytes or b"").decode("utf8")


class CapellaWorkItem(polarion_api.WorkItem):
    """A WorkItem class with additional Capella related attributes."""

    uuid_capella: str
    checksum: str | None
    preCondition: polarion_api.HtmlContent | None
    postCondition: polarion_api.HtmlContent | None
    _content_checksum: str | None = None
    _attachment_checksums: dict[str, str] | None = None

    def clear_attributes(self):
        """Clear all additional attributes except the checksum."""
        # pylint: disable=attribute-defined-outside-init
        self.additional_attributes = {"checksum": self.checksum}
        # pylint: enable=attribute-defined-outside-init

    def _read_check_sum(self):
        checksum_dict = json.loads(self.checksum or "{}")
        self._content_checksum = checksum_dict.pop(WORK_ITEM_CHECKSUM_KEY, "")
        self._attachment_checksums = checksum_dict

    @property
    def content_checksum(self) -> str:
        """Return checksum of the WorkItem content."""
        if self._content_checksum is None:
            self._read_check_sum()
        return self._content_checksum or ""

    @property
    def attachment_checksums(self) -> dict[str, str]:
        """Return attachment checksums."""
        if self._attachment_checksums is None:
            self._read_check_sum()
        assert self._attachment_checksums is not None
        return self._attachment_checksums

    def _calculate_attachment_checksums(self):
        attachment_checksums: dict[str, str] = {}
        attachment_groups: dict[
            str, dict[str, polarion_api.WorkItemAttachment]
        ] = {}
        attachment: polarion_api.WorkItemAttachment | None
        # Attachments are grouped by their file name. Except for SVG/PNG pairs
        # we don't expect multiple files with the same file name. In addition,
        # we don't expect multiple files with the same file name & mime type.
        for attachment in self.attachments:
            assert (
                attachment.file_name is not None
            ), "The file_name must be filled"
            assert (
                attachment.mime_type is not None
            ), "The mime_type must be filled"
            base_file_name = attachment.file_name.rsplit(".", 1)[0]
            attachment_groups.setdefault(base_file_name, {})[
                attachment.mime_type
            ] = attachment

        for base_file_name, attachments in attachment_groups.items():
            if attachment := attachments.pop(SVG_MIME_TYPE, None):
                # For SVGs we expect a PNG to be present
                if png_attachment := attachments.pop(PNG_MIME_TYPE, None):
                    # Only for non context diagrams we use the PNG
                    if not isinstance(
                        attachment, CapellaContextDiagramAttachment
                    ):
                        attachment = png_attachment
                else:
                    logger.warning(
                        "Missing PNG for svg attachment with filename"
                        " %s on WorkItem %s (uuid %s)",
                        base_file_name,
                        self.id,
                        self.uuid_capella,
                    )
            else:
                # In any other case, we just select the next attachments
                _, attachment = attachments.popitem()
            if attachments:
                # There should be no more attachments
                logger.warning(
                    "There are multiple attachments with filename %s in"
                    " WorkItem %s (uuid %s)",
                    base_file_name,
                    self.id,
                    self.uuid_capella,
                )

            if isinstance(attachment, Capella2PolarionAttachment):
                content_checksum = attachment.content_checksum
            else:
                logger.warning(
                    "Found non Capella2PolarionAttachment in the attachments"
                    " of work_item %s (uuid %s) on checksum calculation."
                    " This can cause unexpected behavior.",
                    self.id,
                    self.uuid_capella,
                )
                content_checksum = _calculate_content_checksum(attachment)

            attachment_checksums[base_file_name] = hashlib.sha256(
                json.dumps(
                    {
                        "work_item_id": attachment.work_item_id,
                        "title": attachment.title,
                        "content_bytes": content_checksum,
                        "mime_type": attachment.mime_type,
                        "file_name": attachment.file_name,
                    }
                ).encode("utf8")
            ).hexdigest()

        return dict(sorted(attachment_checksums.items()))

    def calculate_checksum(self) -> str:
        """Calculate and return a checksum for this WorkItem.

        In addition, the checksum will be written to self._checksum.
        Filenames must be unique and same filenames are only valid for
        png&svg pairs.
        """

        data = {
            "title": self.title,
            "description": self.description,
            "type": self.type,
            "status": self.status,
            "additional_attributes": dict(
                sorted(
                    (k, v)
                    for k, v in self.additional_attributes.items()
                    if k != "checksum"
                )
            ),
            "linked_work_items": [
                dataclasses.asdict(lwi)
                for lwi in sorted(
                    self.linked_work_items,
                    key=lambda x: (
                        f"{x.role}/{x.secondary_work_item_project}"
                        f"/{x.secondary_work_item_id}"
                    ),
                )
            ],
            "home_document": (
                dataclasses.asdict(self.home_document)
                if self.home_document
                else None
            ),
        }
        data = dict(sorted(data.items()))
        content_json_str = json.dumps(data).encode("utf8")

        self._content_checksum = hashlib.sha256(content_json_str).hexdigest()
        self._attachment_checksums = self._calculate_attachment_checksums()
        assert self._attachment_checksums is not None
        self.checksum = json.dumps(
            {WORK_ITEM_CHECKSUM_KEY: self._content_checksum}
            | dict(sorted(self._attachment_checksums.items()))
        )
        return self.checksum


@dataclasses.dataclass
class Capella2PolarionAttachment(polarion_api.WorkItemAttachment):
    """Stub Base-Class for Capella2Polarion attachments."""

    _checksum: str | None = None

    @property
    def content_checksum(self) -> str:
        """Calculate the checksum for the content of the attachment."""
        if self._checksum is None:
            self._checksum = _calculate_content_checksum(self)
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
    def content_bytes(self):
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
    def content_checksum(self):
        """Return checksum based on elk input for ContextDiagrams else None."""
        if self._checksum is None:
            elk_input = self.diagram.elk_input_data(self.render_params)
            self._checksum = hashlib.sha256(
                elk_input.json().encode("utf-8")
            ).hexdigest()
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
        ), "PngConvertedSvgAttachment must be initialized using an SVG attachment"
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
    def content_bytes(self):
        """The content bytes are created from the SVG when requested."""
        if not self._content_bytes:
            self._content_bytes = cairosvg.svg2png(
                self._svg_attachment.content_bytes
            )

        return self._content_bytes

    @content_bytes.setter
    def content_bytes(self, value: bytes | None):
        self._content_bytes = value


@dataclasses.dataclass
class DocumentData:
    """A class to store data related to a rendered document."""

    document: polarion_api.Document
    headings: list[polarion_api.WorkItem]
    text_work_item_provider: text_work_item_provider.TextWorkItemProvider


@dataclasses.dataclass
class DocumentInfo:
    """Class for information regarding a document which should be created."""

    project_id: str | None
    module_folder: str
    module_name: str
    text_work_item_type: str
    text_work_item_id_field: str
