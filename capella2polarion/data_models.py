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

import polarion_rest_api_client as polarion_api
from capellambse import model
from capellambse_context_diagrams import context

from capella2polarion.converters import text_work_item_provider

WORK_ITEM_CHECKSUM_KEY = "__C2P__WORK_ITEM"
logger = logging.getLogger(__name__)


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

    def calculate_checksum(self) -> str:
        """Calculate and return a checksum for this WorkItem.

        In addition, the checksum will be written to self._checksum.
        """
        data = self.to_dict()
        if "checksum" in data["additional_attributes"]:
            del data["additional_attributes"]["checksum"]
        del data["id"]

        attachments = data.pop("attachments")
        self._attachment_checksums = {}
        for attachment in attachments:
            # Don't store checksums for SVGs as we can check their PNGs instead
            if attachment["mime_type"] == "image/svg+xml":
                continue
            try:
                attachment["content_bytes"] = base64.b64encode(
                    attachment["content_bytes"]
                ).decode("utf8")
            except TypeError:
                pass

            del attachment["id"]
            self._attachment_checksums[attachment["file_name"]] = (
                hashlib.sha256(
                    json.dumps(attachment).encode("utf8")
                ).hexdigest()
            )

        data = dict(sorted(data.items()))

        converted = json.dumps(data).encode("utf8")
        self._content_checksum = hashlib.sha256(converted).hexdigest()
        self.checksum = json.dumps(
            {WORK_ITEM_CHECKSUM_KEY: self._content_checksum}
            | dict(sorted(self._attachment_checksums.items()))
        )
        return self.checksum


class CapellaDiagramAttachment(polarion_api.WorkItemAttachment):
    """A dedicated attachment type for Capella diagrams."""

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
            "image/svg+xml",
            file_name,
        )
        self.render_params = render_params or {}
        self.diagram = diagram
        self._checksum: str | None = None
        self._content_bytes: bytes | None = None

    @property
    def checksum(self):
        """Return checksum based on elk input for ContextDiagrams else None."""
        if (
            not isinstance(self.diagram, context.ContextDiagram)
            or self._checksum is not None
        ):
            return self._checksum

        elk_input = self.diagram.elk_input_data(self.render_params)
        self._checksum = hashlib.sha256(
            elk_input.json().encode("utf-8")
        ).hexdigest()
        return self._checksum

    @property
    def content_bytes(self):
        """Diagrams are only rendered, if content_bytes are requested."""
        if self._content_bytes:
            return self._content_bytes
        try:
            diagram_svg = self.diagram.render("svg", **self.render_params)
        except Exception:
            logger.exception("Failed to render diagram %s", self.diagram.name)
            diagram_svg = self.diagram.as_svg
        if isinstance(diagram_svg, str):
            diagram_svg = diagram_svg.encode("utf8")
        self._content_bytes = diagram_svg
        return diagram_svg

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
