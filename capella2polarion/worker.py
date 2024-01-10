# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module for polarion API client work."""
from __future__ import annotations

import collections.abc as cabc
import logging
import pathlib
import typing
from typing import Optional
from urllib import parse

import capellambse
import polarion_rest_api_client as polarion_api

from capella2polarion import data_models
from capella2polarion.connectors import polarion_repo
from capella2polarion.converters import (
    converter_config,
    data_session,
    element_converter,
    link_converter,
)

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
        model: capellambse.MelodyModel,
        config: converter_config.ConverterConfig,
        diagram_idx: list[dict[str, typing.Any]],
        diagram_cache_path: pathlib.Path,
    ) -> None:
        self.polarion_params = params
        self.polarion_data_repo = polarion_repo.PolarionDataRepository()
        self.converter_session: data_session.ConverterSession = {}
        self.model = model
        self.config = config
        self.diagram_idx = diagram_idx
        self.diagram_cache_path = diagram_cache_path

        if (self.polarion_params.project_id is None) or (
            len(self.polarion_params.project_id) == 0
        ):
            raise ValueError(
                f"""ProjectId invalid. Value
                '{self._save_value_string(self.polarion_params.project_id)}'"""
            )

        result_url = parse.urlparse(self.polarion_params.url)
        if not all([result_url.scheme, result_url.netloc]):
            raise ValueError(
                f"""Polarion URL parameter is not a valid url.
                Value {self._save_value_string(self.polarion_params.url)}"""
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

    def _save_value_string(self, value: str | None) -> str | None:
        return "None" if value is None else value

    def check_client(self) -> None:
        """Instantiate the polarion client as member."""
        if not self.client.project_exists():
            raise KeyError(
                f"Miss Polarion project with id "
                f"{self._save_value_string(self.polarion_params.project_id)}"
            )

    def generate_converter_session(
        self,
    ) -> None:
        """Return an elements and UUID to Polarion type map."""
        missing_types = set[tuple[str, str, Optional[bool], Optional[str]]]()
        for layer, c_type in self.config.layers_and_types():
            below = getattr(self.model, layer)
            if c_type == "Diagram":
                continue

            objects = self.model.search(c_type, below=below)
            for obj in objects:
                actor = None if not hasattr(obj, "is_actor") else obj.is_actor
                nature = None if not hasattr(obj, "nature") else obj.nature
                if config := self.config.get_type_config(
                    layer, c_type, actor, nature
                ):
                    self.converter_session[
                        obj.uuid
                    ] = data_session.ConverterData(layer, config, obj)
                else:
                    missing_types.add((layer, c_type, actor, nature))

        if self.config.diagram_config:
            diagrams_from_cache = {
                d["uuid"] for d in self.diagram_idx if d["success"]
            }
            for d in self.model.diagrams:
                if d.uuid in diagrams_from_cache:
                    self.converter_session[
                        d.uuid
                    ] = data_session.ConverterData(
                        "", self.config.diagram_config, d
                    )

        if missing_types:
            for missing_type in missing_types:
                logger.warning(
                    "Capella type %r is configured in layer %r, but not for actor %r and nature %r.",
                    *missing_type,
                )

    def load_polarion_work_item_map(self):
        """Return a map from Capella UUIDs to Polarion work items."""
        _type = " ".join(self.config.polarion_types)

        work_items = self.client.get_all_work_items(
            f"type:({_type})",
            {"workitems": "id,uuid_capella,checksum,status"},
        )

        self.polarion_data_repo.update_work_items(work_items)

    def create_work_items(
        self,
    ) -> dict[str, data_models.CapellaWorkItem]:
        """Create a list of work items for Polarion."""
        serializer = element_converter.CapellaWorkItemSerializer(
            self.diagram_cache_path,
            self.model,
            self.polarion_data_repo,
            self.converter_session,
        )
        work_items = serializer.serialize_all()
        for work_item in work_items:
            assert work_item is not None
            assert work_item.title is not None
            assert work_item.type is not None
            if old := self.polarion_data_repo.get_work_item_by_capella_uuid(
                work_item.uuid_capella
            ):
                work_item.id = old.id

        return {wi.uuid_capella: wi for wi in work_items}

    def delete_work_items(self) -> None:
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
        uuids: set[str] = existing_work_items - set(self.converter_session)
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
        self,
    ) -> None:
        """Post work items in a Polarion project."""
        missing_work_items: list[data_models.CapellaWorkItem] = []
        for uuid, converter_data in self.converter_session.items():
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
        self,
        new: data_models.CapellaWorkItem,
        old: data_models.CapellaWorkItem,
    ):
        """Patch a given WorkItem.

        Parameters
        ----------
        api
            The context to execute the patch for.
        new
            The updated CapellaWorkItem
        old
            The CapellaWorkItem currently present on polarion
        """
        if new == old:
            return

        log_args = (old.id, new.type, new.title)
        logger.info("Update work item %r for model %s %r...", *log_args)
        if "uuid_capella" in new.additional_attributes:
            del new.additional_attributes["uuid_capella"]

        old.linked_work_items = self.client.get_all_work_item_links(old.id)
        new.type = None
        new.status = "open"
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
        self,
    ) -> None:
        """Update work items in a Polarion project."""

        back_links: dict[str, list[polarion_api.WorkItemLink]] = {}
        link_serializer = link_converter.LinkSerializer(
            self.polarion_data_repo,
            self.converter_session,
            self.polarion_params.project_id,
            self.model,
        )

        for uuid, converter_data in self.converter_session.items():
            if converter_data.work_item is None:
                logger.warning(
                    "Expected to find a WorkItem for %s, but there is none",
                    uuid,
                )
                continue

            links = link_serializer.create_links_for_work_item(uuid)
            converter_data.work_item.linked_work_items = links

            link_converter.create_grouped_link_fields(
                converter_data.work_item, back_links
            )

        for uuid, converter_data in self.converter_session.items():
            if converter_data.work_item is None:
                logger.warning(
                    "Expected to find a WorkItem for %s, but there is none",
                    uuid,
                )
                continue

            _, old_work_item = self.polarion_data_repo[uuid]
            if old_work_item.id in back_links:
                link_converter.create_grouped_back_link_fields(
                    converter_data.work_item, back_links[old_work_item.id]
                )

            self.patch_work_item(
                converter_data.work_item,
                old_work_item,
            )
