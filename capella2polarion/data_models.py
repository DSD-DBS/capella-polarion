# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module providing the CapellaWorkItem class."""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json

import polarion_rest_api_client as polarion_api

from capella2polarion.converters import text_work_item_provider


class CapellaWorkItem(polarion_api.WorkItem):
    """A WorkItem class with additional Capella related attributes."""

    uuid_capella: str
    checksum: str | None
    preCondition: polarion_api.HtmlContent | None
    postCondition: polarion_api.HtmlContent | None

    def clear_attributes(self):
        """Clear all additional attributes except the checksum."""
        # pylint: disable=attribute-defined-outside-init
        self.additional_attributes = {"checksum": self.checksum}
        # pylint: enable=attribute-defined-outside-init

    def calculate_checksum(self) -> str:
        """Calculate and return a checksum for this WorkItem.

        In addition, the checksum will be written to self._checksum.
        """
        data = self.to_dict()
        if "checksum" in data["additional_attributes"]:
            del data["additional_attributes"]["checksum"]
        del data["id"]

        attachments = data.pop("attachments")
        attachment_checksums = {}
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
            attachment_checksums[attachment["file_name"]] = hashlib.sha256(
                json.dumps(attachment).encode("utf8")
            ).hexdigest()

        data = dict(sorted(data.items()))

        converted = json.dumps(data).encode("utf8")
        self.checksum = json.dumps(
            {"__C2P__WORK_ITEM": hashlib.sha256(converted).hexdigest()}
            | dict(sorted(attachment_checksums.items()))
        )
        return self.checksum


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
