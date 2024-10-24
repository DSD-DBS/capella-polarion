# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module providing data classes for documents."""

from __future__ import annotations

import dataclasses

import polarion_rest_api_client as polarion_api

from capella2polarion.converters import text_work_item_provider

__all__ = ["DocumentData", "DocumentInfo"]


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
