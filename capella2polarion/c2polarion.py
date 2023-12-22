# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module for polarion API client work."""
from __future__ import annotations

import logging
import pathlib
import typing
from itertools import chain
from urllib import parse

import capellambse
import polarion_rest_api_client as polarion_api
from capellambse.model import common

from capella2polarion.elements import api_helper, element, serialize

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
        make_type_id: typing.Any,
    ) -> None:
        self.polarion_params: PolarionWorkerParams = params
        self.elements: dict[str, list[common.GenericElement]] = {}
        self.polarion_type_map: dict[str, str] = {}
        self.capella_uuid_s: set[str] = set()
        self.x_types: set[str] = set()
        self.polarion_id_map: dict[str, str] = {}
        self.polarion_work_item_map: dict[str, serialize.CapellaWorkItem] = {}
        self.make_type_id: typing.Any = make_type_id
        if (self.polarion_params.project_id is None) or (
            len(self.polarion_params.project_id) == 0
        ):
            raise ValueError(
                f"""ProjectId invalid. Value '{self._save_value_string(self.polarion_params.project_id)}'"""
            )

        result_url = parse.urlparse(self.polarion_params.url)
        if not all([result_url.scheme, result_url.netloc]):
            raise ValueError(
                f"""Polarion URL parameter is not a valid url.
                Value {self._save_value_string(self.polarion_params.url)}"""
            )
        if self.polarion_params.private_access_token is None:
            raise ValueError(
                f"""Polarion PAT (Personal Access Token) parameter is not a valid url. Value
                '{self._save_value_string(self.polarion_params.private_access_token)}'"""
            )
        self.client = polarion_api.OpenAPIPolarionProjectClient(
            self.polarion_params.project_id,
            self.polarion_params.delete_work_items,
            polarion_api_endpoint=f"{self.polarion_params.url}/rest/v1",
            polarion_access_token=self.polarion_params.private_access_token,
            custom_work_item=serialize.CapellaWorkItem,
            add_work_item_checksum=True,
        )
        self.check_client()

    def _save_value_string(self, value: str | None) -> str | None:
        return "None" if value is None else value

    def check_client(self) -> None:
        """Instantiate the polarion client, move to PolarionWorker Class."""

        if not self.client.project_exists():
            raise KeyError(
                f"Miss Polarion project with id {self._save_value_string(self.polarion_params.project_id)}"
            )

    def load_elements_and_type_map(
        self,
        config: dict[str, typing.Any],
        model: capellambse.MelodyModel,
        diagram_idx: list[dict[str, typing.Any]],
    ) -> None:
        """Return an elements and UUID to Polarion type map."""
        convert_type = POL2CAPELLA_TYPES
        type_map: dict[str, str] = {}
        elements: dict[str, list[common.GenericElement]] = {}
        for _below, pol_types in config.items():
            below = getattr(model, _below)
            for typ in pol_types:
                if isinstance(typ, dict):
                    typ = list(typ.keys())[0]

                if typ == "Diagram":
                    continue

                xtype = convert_type.get(typ, typ)
                objects = model.search(xtype, below=below)
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
            d for d in model.diagrams if d.uuid in diagrams_from_cache
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

        self.polarion_work_item_map = {
            wi.uuid_capella: wi
            for wi in work_items
            if wi.id and wi.uuid_capella
        }
        self.polarion_id_map = {
            uuid: wi.id for uuid, wi in self.polarion_work_item_map.items()
        }

    def create_work_items(
        self,
        diagram_cache_path: pathlib.Path,
        model,
        descr_references: dict[str, list[str]],
    ) -> dict[str, serialize.CapellaWorkItem]:
        """Create a list of work items for Polarion."""
        objects = chain.from_iterable(self.elements.values())
        _work_items = []
        serializer = serialize.CapellaWorkItemSerializer(
            diagram_cache_path,
            self.polarion_type_map,
            model,
            self.polarion_id_map,
            descr_references,
        )
        for obj in objects:
            _work_items.append(serializer.serialize(obj))

        _work_items = list(filter(None, _work_items))
        valid_types = set(map(self.make_type_id, set(self.elements)))
        work_items: list[serialize.CapellaWorkItem] = []
        missing_types: set[str] = set()
        for work_item in _work_items:
            assert work_item is not None
            assert work_item.title is not None
            assert work_item.type is not None
            if old := self.polarion_work_item_map.get(work_item.uuid_capella):
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
            logger.info(
                "Delete work item %r...",
                workitem_id := self.polarion_id_map[uuid],
            )
            return workitem_id

        existing_work_items = {
            uuid
            for uuid, work_item in self.polarion_work_item_map.items()
            if work_item.status != "deleted"
        }
        uuids: set[str] = existing_work_items - self.capella_uuid_s
        work_item_ids = [serialize_for_delete(uuid) for uuid in uuids]
        if work_item_ids:
            try:
                self.client.delete_work_items(work_item_ids)
                for uuid in uuids:
                    del self.polarion_work_item_map[uuid]
                    del self.polarion_id_map[uuid]
            except polarion_api.PolarionApiException as error:
                logger.error("Deleting work items failed. %s", error.args[0])

    def post_work_items(
        self, new_work_items: dict[str, serialize.CapellaWorkItem]
    ) -> None:
        """Post work items in a Polarion project."""
        missing_work_items: list[serialize.CapellaWorkItem] = []
        for work_item in new_work_items.values():
            if work_item.uuid_capella in self.polarion_id_map:
                continue

            assert work_item is not None
            missing_work_items.append(work_item)
            logger.info("Create work item for %r...", work_item.title)
        if missing_work_items:
            try:
                self.client.create_work_items(missing_work_items)
                for work_item in missing_work_items:
                    self.polarion_id_map[work_item.uuid_capella] = work_item.id
                    self.polarion_work_item_map[
                        work_item.uuid_capella
                    ] = work_item
            except polarion_api.PolarionApiException as error:
                logger.error("Creating work items failed. %s", error.args[0])

    def patch_work_items(
        self,
        model: capellambse.MelodyModel,
        new_work_items: dict[str, serialize.CapellaWorkItem],
        descr_references,
        link_roles,
    ) -> None:
        """Update work items in a Polarion project."""
        self.polarion_id_map = {
            uuid: wi.id
            for uuid, wi in self.polarion_work_item_map.items()
            if wi.status == "open" and wi.uuid_capella and wi.id
        }

        back_links: dict[str, list[polarion_api.WorkItemLink]] = {}
        for uuid in self.polarion_id_map:
            objects = model
            if uuid.startswith("_"):
                objects = model.diagrams
            obj = objects.by_uuid(uuid)

            links = element.create_links(
                obj,
                self.polarion_id_map,
                self.polarion_work_item_map,
                descr_references,
                self.polarion_params.project_id,
                model,
                link_roles,
            )
            work_item: serialize.CapellaWorkItem = new_work_items[uuid]
            work_item.linked_work_items = links

            element.create_grouped_link_fields(work_item, back_links)

        for uuid in self.polarion_id_map:
            new_work_item: serialize.CapellaWorkItem = new_work_items[uuid]
            old_work_item = self.polarion_work_item_map[uuid]
            if old_work_item.id in back_links:
                element.create_grouped_back_link_fields(
                    new_work_item, back_links[old_work_item.id]
                )

            api_helper.patch_work_item(
                self.client,
                new_work_item,
                old_work_item,
            )
