# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module for polarion API client work."""
from __future__ import annotations

import collections.abc as cabc
import logging
import typing as t
from urllib import parse

import polarion_rest_api_client as polarion_api

from capella2polarion import data_models
from capella2polarion.connectors import polarion_repo
from capella2polarion.converters import converter_config, data_session

logger = logging.getLogger(__name__)


class PolarionWorkerParams:
    """Container for Polarion Params."""

    def __init__(
        self, project_id: str, url: str, pat: str, delete_work_items: bool
    ) -> None:
        self.project_id = project_id
        self.url = url
        self.private_access_token = pat
        self.delete_work_items = delete_work_items


class CapellaPolarionWorker:
    """CapellaPolarionWorker encapsulate the Polarion API Client work."""

    def __init__(
        self,
        params: PolarionWorkerParams,
        config: converter_config.ConverterConfig,
        force_update: bool = False,
    ) -> None:
        self.polarion_params = params
        self.polarion_data_repo = polarion_repo.PolarionDataRepository()
        self.config = config
        self.force_update = force_update

        if (self.polarion_params.project_id is None) or (
            len(self.polarion_params.project_id) == 0
        ):
            raise ValueError(
                f"""ProjectId invalid. Value
                '{self.polarion_params.project_id}'"""
            )

        result_url = parse.urlparse(self.polarion_params.url)
        if not all([result_url.scheme, result_url.netloc]):
            raise ValueError(
                f"""Polarion URL parameter is not a valid url.
                Value {self.polarion_params.url}"""
            )
        if self.polarion_params.private_access_token is None:
            raise ValueError(
                "Polarion PAT (Personal Access Token) parameter "
                "is not a set properly."
            )
        self.client = polarion_api.OpenAPIPolarionProjectClient(
            self.polarion_params.project_id,
            self.polarion_params.delete_work_items,
            polarion_api_endpoint=f"{self.polarion_params.url}/rest/v1",
            polarion_access_token=self.polarion_params.private_access_token,
            custom_work_item=data_models.CapellaWorkItem,
            add_work_item_checksum=True,
        )
        self.check_client()

    def check_client(self) -> None:
        """Instantiate the polarion client as member."""
        if not self.client.project_exists():
            raise KeyError(
                f"Miss Polarion project with id "
                f"{self.polarion_params.project_id}"
            )

    def load_polarion_work_item_map(self):
        """Return a map from Capella UUIDs to Polarion work items."""
        _type = " ".join(self.config.polarion_types)

        work_items = self.client.get_all_work_items(
            f"type:({_type})",
            {"workitems": "id,uuid_capella,checksum,status"},
        )

        self.polarion_data_repo.update_work_items(work_items)

    def delete_work_items(
        self, converter_session: data_session.ConverterSession
    ) -> None:
        """Delete work items in a Polarion project.

        If the delete flag is set to ``False`` in the context work items are
        marked as ``to be deleted`` via the status attribute.
        """

        def serialize_for_delete(uuid: str) -> str:
            work_item_id, _ = self.polarion_data_repo[uuid]
            logger.info("Delete work item %r...", work_item_id)
            return work_item_id

        existing_work_items = {
            uuid
            for uuid, _, work_item in self.polarion_data_repo.items()
            if work_item.status != "deleted"
        }
        uuids: set[str] = existing_work_items - set(converter_session)
        work_item_ids = [serialize_for_delete(uuid) for uuid in uuids]
        if work_item_ids:
            try:
                self.client.delete_work_items(work_item_ids)
                self.polarion_data_repo.remove_work_items_by_capella_uuid(
                    uuids
                )
            except polarion_api.PolarionApiException as error:
                logger.error("Deleting work items failed. %s", error.args[0])

    def post_work_items(
        self, converter_session: data_session.ConverterSession
    ) -> None:
        """Post work items in a Polarion project."""
        missing_work_items: list[data_models.CapellaWorkItem] = []
        for uuid, converter_data in converter_session.items():
            work_item = converter_data.work_item
            if work_item is None:
                logger.warning(
                    "Expected to find a WorkItem for %s, but there is none",
                    uuid,
                )
                continue

            if work_item.uuid_capella in self.polarion_data_repo:
                continue

            assert work_item is not None
            missing_work_items.append(work_item)
            logger.info("Create work item for %r...", work_item.title)
        if missing_work_items:
            try:
                self.client.create_work_items(missing_work_items)
                self.polarion_data_repo.update_work_items(missing_work_items)
            except polarion_api.PolarionApiException as error:
                logger.error("Creating work items failed. %s", error.args[0])

    def patch_work_item(
        self, uuid: str, converter_session: data_session.ConverterSession
    ):
        """Patch a given WorkItem."""
        new = converter_session[uuid].work_item
        _, old = self.polarion_data_repo[uuid]
        if not self.force_update and new == old:
            return

        assert old is not None
        assert new is not None

        log_args = (old.id, new.type, new.title)
        logger.info("Update work item %r for model %s %r...", *log_args)

        del new.additional_attributes["uuid_capella"]

        old = self.client.get_work_item(old.id)

        # If there were to many linked work items, get them manually
        if old.linked_work_items_truncated:
            old.linked_work_items = self.client.get_all_work_item_links(old.id)

        del old.additional_attributes["uuid_capella"]

        # We should only send the type to be updated, if it really changed
        if new.type == old.type:
            new.type = None
        new.status = "open"

        # If additional fields were present in the past, but aren't anymore,
        # we have to set them to an empty value manually
        for attribute, value in old.additional_attributes.items():
            if attribute not in new.additional_attributes:
                new_value: t.Any = None
                if isinstance(value, str):
                    new_value = ""
                elif isinstance(value, int):
                    new_value = 0
                elif isinstance(value, bool):
                    new_value = False
                new.additional_attributes[attribute] = new_value
            elif new.additional_attributes[attribute] == value:
                del new.additional_attributes[attribute]

        assert new.id is not None
        try:
            self.client.update_work_item(new)
            if delete_link_ids := CapellaPolarionWorker.get_missing_link_ids(
                old.linked_work_items, new.linked_work_items
            ):
                id_list_str = ", ".join(delete_link_ids.keys())
                logger.info(
                    "Delete work item links %r for model %s %r",
                    id_list_str,
                    new.type,
                    new.title,
                )
                self.client.delete_work_item_links(
                    list(delete_link_ids.values())
                )

            if create_links := CapellaPolarionWorker.get_missing_link_ids(
                new.linked_work_items, old.linked_work_items
            ):
                id_list_str = ", ".join(create_links.keys())
                logger.info(
                    "Create work item links %r for model %s %r",
                    id_list_str,
                    new.type,
                    new.title,
                )
                self.client.create_work_item_links(list(create_links.values()))

        except polarion_api.PolarionApiException as error:
            logger.error(
                "Updating work item %r (%s %s) failed. %s",
                *log_args,
                error.args[0],
            )

    @staticmethod
    def get_missing_link_ids(
        left: cabc.Iterable[polarion_api.WorkItemLink],
        right: cabc.Iterable[polarion_api.WorkItemLink],
    ) -> dict[str, polarion_api.WorkItemLink]:
        """Return an ID-Link dict of links present in left and not in right."""
        left_id_map = {
            CapellaPolarionWorker._get_link_id(link): link for link in left
        }
        right_id_map = {
            CapellaPolarionWorker._get_link_id(link): link for link in right
        }
        return {
            lid: left_id_map[lid]
            for lid in set(left_id_map) - set(right_id_map)
        }

    @staticmethod
    def _get_link_id(link: polarion_api.WorkItemLink) -> str:
        return "/".join(
            (
                link.primary_work_item_id,
                link.role,
                link.secondary_work_item_project,
                link.secondary_work_item_id,
            )
        )

    def patch_work_items(
        self, converter_session: data_session.ConverterSession
    ) -> None:
        """Update work items in a Polarion project."""
        for uuid in converter_session:
            self.patch_work_item(uuid, converter_session)
