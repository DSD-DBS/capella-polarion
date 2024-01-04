# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module for polarion API client work."""
from __future__ import annotations

import collections.abc as cabc
import logging
import pathlib
import typing
from itertools import chain
from urllib import parse

import capellambse
import polarion_rest_api_client as polarion_api
from capellambse.model import common

from capella2polarion import capella_work_item
from capella2polarion.capella_polarion_conversion import (
    element_converter,
    link_converter,
)
from capella2polarion.polarion_connector import polarion_repo

logger = logging.getLogger(__name__)

# STATUS_DELETE = "deleted"
ACTOR_TYPES = {
    "LogicalActor": "LogicalComponent",
    "SystemActor": "SystemComponent",
    "PhysicalActor": "PhysicalComponent",
}
PHYSICAL_COMPONENT_TYPES = {
    "PhysicalComponentNode": "PhysicalComponent",
    "PhysicalActorNode": "PhysicalComponent",
    "PhysicalComponentBehavior": "PhysicalComponent",
    "PhysicalActorBehavior": "PhysicalComponent",
}
POL2CAPELLA_TYPES: dict[str, str] = (
    {
        "OperationalEntity": "Entity",
        "OperationalInteraction": "FunctionalExchange",
        "SystemCapability": "Capability",
    }
    | ACTOR_TYPES
    | PHYSICAL_COMPONENT_TYPES
)
TYPES_POL2CAPELLA = {
    ctype: ptype for ptype, ctype in POL2CAPELLA_TYPES.items()
}


class PolarionWorkerParams:
    """Container for Polarion Params."""

    def __init__(
        self, project_id: str, url: str, pat: str, delete_work_items: bool
    ) -> None:
        self.project_id = project_id
        self.url = url
        self.private_access_token = pat
        self.delete_work_items = delete_work_items


class PolarionWorker:
    """PolarionWorker encapsulate the Polarion API Client work."""

    def __init__(
        self,
        params: PolarionWorkerParams,
        model: capellambse.MelodyModel,
        make_type_id: typing.Any,
    ) -> None:
        self.polarion_params: PolarionWorkerParams = params
        self.elements: dict[str, list[common.GenericElement]] = {}
        self.polarion_type_map: dict[str, str] = {}  # TODO refactor
        self.capella_uuid_s: set[str] = set()  # TODO refactor
        self.x_types: set[str] = set()
        self.polarion_data_repo = polarion_repo.PolarionDataRepository()
        self.model = model
        self.make_type_id: typing.Any = make_type_id
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
            custom_work_item=capella_work_item.CapellaWorkItem,
            add_work_item_checksum=True,
        )
        self.check_client()

    def _save_value_string(self, value: str | None) -> str | None:
        return "None" if value is None else value

    def check_client(self) -> None:
        """Instantiate the polarion client, move to PolarionWorker Class."""

        if not self.client.project_exists():
            raise KeyError(
                f"Miss Polarion project with id "
                f"{self._save_value_string(self.polarion_params.project_id)}"
            )

    def load_elements_and_type_map(
        self,
        config: dict[str, typing.Any],
        diagram_idx: list[dict[str, typing.Any]],
    ) -> None:
        """Return an elements and UUID to Polarion type map."""
        convert_type = POL2CAPELLA_TYPES
        type_map: dict[str, str] = {}
        elements: dict[str, list[common.GenericElement]] = {}
        for _below, pol_types in config.items():
            below = getattr(self.model, _below)
            for typ in pol_types:
                if isinstance(typ, dict):
                    typ = list(typ.keys())[0]

                if typ == "Diagram":
                    continue

                xtype = convert_type.get(typ, typ)
                objects = self.model.search(xtype, below=below)
                elements.setdefault(typ, []).extend(objects)
                for obj in objects:
                    type_map[obj.uuid] = typ

        for typ, xtype in ACTOR_TYPES.items():
            if typ not in elements:
                continue

            actors: list[common.GenericElement] = []
            components: list[common.GenericElement] = []
            for obj in elements[typ]:
                if obj.is_actor:
                    actors.append(obj)
                else:
                    components.append(obj)
                    type_map[obj.uuid] = xtype

            elements[typ] = actors
            elements[xtype] = components

        nature_mapping: dict[str, tuple[list[common.GenericElement], str]] = {
            "UNSET": ([], "PhysicalComponent"),
            "NODE": ([], "PhysicalComponentNode"),
            "BEHAVIOR": ([], "PhysicalComponentBehavior"),
            "NODE_actor": ([], "PhysicalActorNode"),
            "BEHAVIOR_actor": ([], "PhysicalActorBehavior"),
        }
        for obj in elements.get("PhysicalComponent", []):
            postfix = "_actor" if obj.is_actor else ""
            container, xtype = nature_mapping[f"{str(obj.nature)}{postfix}"]
            container.append(obj)
            type_map[obj.uuid] = xtype

        for container, xtype in nature_mapping.values():
            if container:
                elements[xtype] = container

        diagrams_from_cache = {d["uuid"] for d in diagram_idx if d["success"]}
        elements["Diagram"] = [
            d for d in self.model.diagrams if d.uuid in diagrams_from_cache
        ]
        for obj in elements["Diagram"]:
            type_map[obj.uuid] = "Diagram"
        self.elements = elements
        self.polarion_type_map = type_map
        self.capella_uuid_s = set(self.polarion_type_map)

    def fill_xtypes(self):
        """Return a set of Polarion types from the current context."""
        xtypes = set[str]()
        for obj in chain.from_iterable(self.elements.values()):
            xtype = self.polarion_type_map.get(obj.uuid, type(obj).__name__)
            xtypes.add(self.make_type_id(xtype))
        self.x_types = xtypes

    def load_polarion_work_item_map(self):
        """Return a map from Capella UUIDs to Polarion work items."""
        work_item_types = list(map(self.make_type_id, self.x_types))
        _type = " ".join(work_item_types)

        work_items = self.client.get_all_work_items(
            f"type:({_type})",
            {"workitems": "id,uuid_capella,checksum,status"},
        )

        self.polarion_data_repo.update_work_items(work_items)

    def create_work_items(
        self,
        diagram_cache_path: pathlib.Path,
        model,
        descr_references: dict[str, list[str]],
    ) -> dict[str, capella_work_item.CapellaWorkItem]:
        """Create a list of work items for Polarion."""
        objects = chain.from_iterable(self.elements.values())
        _work_items = []
        serializer = element_converter.CapellaWorkItemSerializer(
            diagram_cache_path,
            self.polarion_type_map,
            model,
            self.polarion_data_repo,
            descr_references,
        )
        for obj in objects:
            _work_items.append(serializer.serialize(obj))

        _work_items = list(filter(None, _work_items))
        valid_types = set(map(self.make_type_id, set(self.elements)))
        work_items: list[capella_work_item.CapellaWorkItem] = []
        missing_types: set[str] = set()
        for work_item in _work_items:
            assert work_item is not None
            assert work_item.title is not None
            assert work_item.type is not None
            if old := self.polarion_data_repo.get_work_item_by_capella_uuid(
                work_item.uuid_capella
            ):
                work_item.id = old.id
            if work_item.type in valid_types:
                work_items.append(work_item)
            else:
                missing_types.add(work_item.type)

        if missing_types:
            logger.debug(
                "%r are missing in the capella2polarion configuration",
                ", ".join(missing_types),
            )
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
        uuids: set[str] = existing_work_items - self.capella_uuid_s
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
        self, new_work_items: dict[str, capella_work_item.CapellaWorkItem]
    ) -> None:
        """Post work items in a Polarion project."""
        missing_work_items: list[capella_work_item.CapellaWorkItem] = []
        for work_item in new_work_items.values():
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
        new: capella_work_item.CapellaWorkItem,
        old: capella_work_item.CapellaWorkItem,
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
            if delete_link_ids := PolarionWorker.get_missing_link_ids(
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

            if create_links := PolarionWorker.get_missing_link_ids(
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
            PolarionWorker._get_link_id(link): link for link in left
        }
        right_id_map = {
            PolarionWorker._get_link_id(link): link for link in right
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
        new_work_items: dict[str, capella_work_item.CapellaWorkItem],
        descr_references,
        link_roles,
    ) -> None:
        """Update work items in a Polarion project."""

        back_links: dict[str, list[polarion_api.WorkItemLink]] = {}
        link_serializer = link_converter.LinkSerializer(
            self.polarion_data_repo,
            new_work_items,
            descr_references,
            self.polarion_params.project_id,
            self.model,
        )

        for uuid in new_work_items:
            objects = self.model
            if uuid.startswith("_"):
                objects = self.model.diagrams
            obj = objects.by_uuid(uuid)

            links = link_serializer.create_links_for_work_item(
                obj,
                link_roles,
            )
            work_item: capella_work_item.CapellaWorkItem = new_work_items[uuid]
            work_item.linked_work_items = links

            link_converter.create_grouped_link_fields(work_item, back_links)

        for uuid, _, old_work_item in self.polarion_data_repo.items():
            new_work_item: capella_work_item.CapellaWorkItem = new_work_items[
                uuid
            ]
            if old_work_item.id in back_links:
                link_converter.create_grouped_back_link_fields(
                    new_work_item, back_links[old_work_item.id]
                )

            self.patch_work_item(
                new_work_item,
                old_work_item,
            )
