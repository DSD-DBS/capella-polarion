# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module for polarion API client work."""
import logging
import pathlib
import typing
from itertools import chain

import capellambse
import polarion_rest_api_client as polarion_api
from capellambse.model import common

import capella2polarion
from capella2polarion.elements import api_helper, element, serialize

GLogger = logging.getLogger(__name__)

# STATUS_DELETE = "deleted"
ACTOR_TYPES = {
    "LogicalActor": "LogicalComponent",
    "SystemActor": "SystemComponent",
    "PhysicalActor": "PhysicalComponent",
}
PHYSICAL_COMPONENT_TYPES = {
    "PhysicalComponentNode": "PhysicalComponent",
    "PhysicalComponentBehavior": "PhysicalComponent",
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


class PolarionWorker:
    """PolarionWorker encapsulate the Polarion API Client work."""

    def __init__(
        self,
        aPolarionClient: polarion_api.OpenAPIPolarionProjectClient,
        aLogger: logging.Logger,
        aMakeTypeId: typing.Any,
    ) -> None:
        self.client: polarion_api.OpenAPIPolarionProjectClient = (
            aPolarionClient
        )
        self.logger: logging.Logger = aLogger
        self.Elements: dict[str, list[common.GenericElement]]
        self.PolarionTypeMap: dict[str, str] = {}
        self.CapellaUUIDs: set[str] = set()
        self.XTypes: set[str] = set()
        self.PolarionIdMap: dict[str, str] = {}
        self.PolarionWorkItemMap: dict[
            str, serialize.CapellaWorkItem
        ]  # dict[str, typing.Any] = None
        self.makeTypeId: typing.Any = aMakeTypeId
        self.Simulation: bool = True

    def load_elements_and_type_map(
        self,
        config: dict[str, typing.Any],
        model: capellambse.MelodyModel,
        diagram_idx: list[dict[str, typing.Any]],
    ) -> None:
        """Return an elements and UUID to Polarion type map."""

        def _fix_components(
            elements: dict[str, list[common.GenericElement]],
            type_map: dict[str, str],
        ) -> None:
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

            nodes: list[common.GenericElement] = []
            behaviors: list[common.GenericElement] = []
            components = []
            for obj in elements.get("PhysicalComponent", []):
                if obj.nature is not None and obj.nature.name == "NODE":
                    nodes.append(obj)
                    type_map[obj.uuid] = "PhysicalComponentNode"
                elif obj.nature is not None and obj.nature.name == "BEHAVIOR":
                    behaviors.append(obj)
                    type_map[obj.uuid] = "PhysicalComponentBehavior"
                else:
                    components.append(obj)

            if nodes:
                elements["PhysicalComponentNode"] = nodes
            if behaviors:
                elements["PhysicalComponentBehavior"] = behaviors
            if components:
                elements["PhysicalComponent"] = components

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

        _fix_components(elements, type_map)
        diagrams_from_cache = {d["uuid"] for d in diagram_idx if d["success"]}
        elements["Diagram"] = [
            d for d in model.diagrams if d.uuid in diagrams_from_cache
        ]
        for obj in elements["Diagram"]:
            type_map[obj.uuid] = "Diagram"
        self.Elements = elements
        self.PolarionTypeMap = type_map
        self.CapellaUUIDs = set(self.PolarionTypeMap)

    def fill_xtypes(self):
        """Return a set of Polarion types from the current context."""
        xtypes = set[str]()
        for obj in chain.from_iterable(self.Elements.values()):
            xtype = self.PolarionTypeMap.get(obj.uuid, type(obj).__name__)
            xtypes.add(self.makeTypeId(xtype))
        self.XTypes = xtypes

    def load_polarion_work_item_map(self):
        """Return a map from Capella UUIDs to Polarion work items."""
        work_item_types = list(map(self.makeTypeId, self.XTypes))
        _type = " ".join(work_item_types)
        if self.Simulation:
            work_item = serialize.CapellaWorkItem(
                "84a64a2d-3491-48af-b55b-823010a3e006", "FakeItem"
            )
            work_item.uuid_capella = "weck"
            work_item.checksum = "doppelwegg"
            work_item.status = "fake"
            work_items = []
            work_items.append(work_item)
        else:
            work_items = self.client.get_all_work_items(
                f"type:({_type})",
                {"workitems": "id,uuid_capella,checksum,status"},
            )
        self.PolarionWorkItemMap = {
            wi.uuid_capella: wi
            for wi in work_items
            if wi.id and wi.uuid_capella
        }
        self.PolarionIdMap = {
            uuid: wi.id for uuid, wi in self.PolarionWorkItemMap.items()
        }

    def create_work_items(
        self,
        aDiagramCachePath: pathlib.Path,
        model,
        descr_references: dict[str, list[str]],
    ) -> dict[str, serialize.CapellaWorkItem]:
        """Create a list of work items for Polarion."""
        objects = chain.from_iterable(self.Elements.values())
        _work_items = []
        serializer = serialize.CapellaWorkItemSerializer(
            aDiagramCachePath,
            self.PolarionTypeMap,
            model,
            self.PolarionIdMap,
            descr_references,
        )
        for obj in objects:
            _work_items.append(serializer.serialize(obj))

        _work_items = list(filter(None, _work_items))
        valid_types = set(map(self.makeTypeId, set(self.Elements)))
        work_items: list[serialize.CapellaWorkItem] = []
        missing_types: set[str] = set()
        for work_item in _work_items:
            assert work_item is not None
            if work_item.type in valid_types:
                work_items.append(work_item)
            else:
                missing_types.add(work_item.type)

        if missing_types:
            self.logger.debug(
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
            self.logger.info(
                "Delete work item %r...",
                workitem_id := self.PolarionIdMap[uuid],
            )
            return workitem_id

        existing_work_items = {
            uuid
            for uuid, work_item in self.PolarionWorkItemMap.items()
            if work_item.status != "deleted"
        }
        uuids: set[str] = existing_work_items - self.CapellaUUIDs
        work_item_ids = [serialize_for_delete(uuid) for uuid in uuids]
        if work_item_ids:
            try:
                if not self.Simulation:
                    self.client.delete_work_items(work_item_ids)
                for uuid in uuids:
                    del self.PolarionWorkItemMap[uuid]
                    del self.PolarionIdMap[uuid]
            except polarion_api.PolarionApiException as error:
                self.logger.error(
                    "Deleting work items failed. %s", error.args[0]
                )

    def post_work_items(
        self, new_work_items: dict[str, serialize.CapellaWorkItem]
    ) -> None:
        """Post work items in a Polarion project."""
        missing_work_items: list[serialize.CapellaWorkItem] = []
        for work_item in new_work_items.values():
            if work_item.uuid_capella in self.PolarionIdMap:
                continue

            assert work_item is not None
            missing_work_items.append(work_item)
            self.logger.info("Create work item for %r...", work_item.title)
        if missing_work_items:
            try:
                if not self.Simulation:
                    self.client.create_work_items(missing_work_items)
                for work_item in missing_work_items:
                    self.PolarionIdMap[work_item.uuid_capella] = work_item.id
                    self.PolarionWorkItemMap[
                        work_item.uuid_capella
                    ] = work_item
            except polarion_api.PolarionApiException as error:
                self.logger.error(
                    "Creating work items failed. %s", error.args[0]
                )

    def patch_work_items(
        self,
        model: capellambse.MelodyModel,
        new_work_items: dict[str, serialize.CapellaWorkItem],
        descr_references,
        project_id,
        link_roles,
    ) -> None:
        """Update work items in a Polarion project."""
        self.PolarionIdMap.update(
            {
                uuid: wi.id
                for uuid, wi in self.PolarionWorkItemMap.items()
                if wi.status == "open" and wi.uuid_capella and wi.id
            }
        )

        back_links: dict[str, list[polarion_api.WorkItemLink]] = {}
        for uuid in self.PolarionIdMap:
            objects = model
            if uuid.startswith("_"):
                objects = model.diagrams
            obj = objects.by_uuid(uuid)

            links = element.create_links(
                obj,
                self.PolarionIdMap,
                descr_references,
                project_id,
                model,
                link_roles,
                TYPES_POL2CAPELLA,
            )
            work_item: serialize.CapellaWorkItem = new_work_items[uuid]
            work_item.linked_work_items = links

            element.create_grouped_link_fields(work_item, back_links)

        for uuid in self.PolarionIdMap:
            new_work_item: serialize.CapellaWorkItem = new_work_items[uuid]
            old_work_item = self.PolarionWorkItemMap[uuid]
            if old_work_item.id in back_links:
                element.create_grouped_back_link_fields(
                    new_work_item, back_links[old_work_item.id]
                )
            if not self.Simulation:
                api_helper.patch_work_item(
                    self.client,
                    new_work_item,
                    old_work_item,
                    old_work_item.title,
                    "element",
                )
