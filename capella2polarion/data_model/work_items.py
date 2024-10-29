# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module providing the CapellaWorkItem class."""
from __future__ import annotations

import dataclasses
import hashlib
import json
import logging

import polarion_rest_api_client as polarion_api

from capella2polarion.data_model import work_item_attachments as wi_att

WORK_ITEM_CHECKSUM_KEY = "__C2P__WORK_ITEM"
logger = logging.getLogger(__name__)


__all__ = ["CapellaWorkItem"]


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

    def _calculate_attachment_checksums(self) -> dict[str, str]:
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
            if attachment := attachments.pop(wi_att.SVG_MIME_TYPE, None):
                # For SVGs we expect a PNG to be present
                if png_attachment := attachments.pop(
                    wi_att.PNG_MIME_TYPE, None
                ):
                    # Only for non context diagrams we use the PNG
                    if not isinstance(
                        attachment, wi_att.CapellaContextDiagramAttachment
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

            if isinstance(attachment, wi_att.Capella2PolarionAttachment):
                content_checksum = attachment.content_checksum
            else:
                logger.warning(
                    "Found non Capella2PolarionAttachment in the attachments"
                    " of work_item %s (uuid %s) on checksum calculation."
                    " This can cause unexpected behavior.",
                    self.id,
                    self.uuid_capella,
                )
                content_checksum = wi_att.calculate_content_checksum(
                    attachment
                )

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
