# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Objects for synchronization of capella objects to polarion workitems."""

# from __future__ import annotations

# __all__ = [
#     "delete_work_items",
#     "get_types",
#     "get_elements_and_type_map",
#     "STATUS_DELETE",
# ]


# logger = logging.getLogger(__name__)

# STATUS_DELETE = "deleted"
# ACTOR_TYPES = {
#     "LogicalActor": "LogicalComponent",
#     "SystemActor": "SystemComponent",
#     "PhysicalActor": "PhysicalComponent",
# }
# PHYSICAL_COMPONENT_TYPES = {
#     "PhysicalComponentNode": "PhysicalComponent",
#     "PhysicalComponentBehavior": "PhysicalComponent",
# }
# POL2CAPELLA_TYPES: dict[str, str] = (
#     {
#         "OperationalEntity": "Entity",
#         "OperationalInteraction": "FunctionalExchange",
#         "SystemCapability": "Capability",
#     }
#     | ACTOR_TYPES
#     | PHYSICAL_COMPONENT_TYPES
# )


# def get_polarion_wi_map(
#     _types: set, api_client: polarion_api.OpenAPIPolarionProjectClient
# ) -> dict[str, t.Any]:
#     """Return a map from Capella UUIDs to Polarion work items."""
#     work_item_types = list(map(helpers.resolve_element_type, _types))
#     _type = " ".join(work_item_types)
#     work_items = api_client.get_all_work_items(
#         f"type:({_type})", {"workitems": "id,uuid_capella,checksum,status"}
#     )
#     return {
#         wi.uuid_capella: wi for wi in work_items if wi.id and wi.uuid_capella
#     }


# def delete_work_items(
#     polarion_id_map: dict[str, str],
#     polarion_wi_map: dict[str, serialize.CapellaWorkItem],
#     capella_uuids: set[str],
#     api_client: polarion_api.OpenAPIPolarionProjectClient,
# ) -> None:
#     """Delete work items in a Polarion project.

#     If the delete flag is set to ``False`` in the context work items are
#     marked as ``to be deleted`` via the status attribute.
#     """

#     def serialize_for_delete(uuid: str) -> str:
#         logger.info(
#             "Delete work item %r...",
#             workitem_id := polarion_id_map[uuid],
#         )
#         return workitem_id

#     existing_work_items = {
#         uuid
#         for uuid, work_item in polarion_wi_map.items()
#         if work_item.status != "deleted"
#     }
#     uuids: set[str] = existing_work_items - capella_uuids
#     work_item_ids = [serialize_for_delete(uuid) for uuid in uuids]
#     if work_item_ids:
#         try:
#             api_client.delete_work_items(work_item_ids)
#             for uuid in uuids:
#                 del polarion_wi_map[uuid]
#                 del polarion_id_map[uuid]
#         except polarion_api.PolarionApiException as error:
#             logger.error("Deleting work items failed. %s", error.args[0])


# def post_work_items(
#     polarion_id_map: dict[str, str],
#     new_work_items: dict[str, serialize.CapellaWorkItem],
#     polarion_wi_map: dict[str, serialize.CapellaWorkItem],
#     api_client: polarion_api.OpenAPIPolarionProjectClient,
# ) -> None:
#     """Post work items in a Polarion project."""
#     missing_work_items: list[serialize.CapellaWorkItem] = []
#     for work_item in new_work_items.values():
#         if work_item.uuid_capella in polarion_id_map:
#             continue

#         assert work_item is not None
#         missing_work_items.append(work_item)
#         logger.info("Create work item for %r...", work_item.title)
#     if missing_work_items:
#         try:
#             api_client.create_work_items(missing_work_items)
#             for work_item in missing_work_items:
#                 polarion_id_map[work_item.uuid_capella] = work_item.id
#                 polarion_wi_map[work_item.uuid_capella] = work_item
#         except polarion_api.PolarionApiException as error:
#             logger.error("Creating work items failed. %s", error.args[0])


# def patch_work_items(
#     polarion_id_map: dict[str, str],
#     model: capellambse.MelodyModel,
#     new_work_items: dict[str, serialize.CapellaWorkItem],
#     polarion_wi_map: dict[str, serialize.CapellaWorkItem],
#     api_client: polarion_api.OpenAPIPolarionProjectClient,
#     descr_references,
#     project_id,
#     link_roles,
# ) -> None:
#     """Update work items in a Polarion project."""
#     polarion_id_map.update(
#         {
#             uuid: wi.id
#             for uuid, wi in polarion_wi_map.items()
#             if wi.status == "open" and wi.uuid_capella and wi.id
#         }
#     )

#     back_links: dict[str, list[polarion_api.WorkItemLink]] = {}
#     for uuid in polarion_id_map:
#         objects = model
#         if uuid.startswith("_"):
#             objects = model.diagrams
#         obj = objects.by_uuid(uuid)

#         links = element.create_links(
#             obj,
#             polarion_id_map,
#             descr_references,
#             project_id,
#             model,
#             link_roles,
#         )
#         work_item: serialize.CapellaWorkItem = new_work_items[uuid]
#         work_item.linked_work_items = links

#         element.create_grouped_link_fields(work_item, back_links)

#     for uuid in polarion_id_map:
#         new_work_item: serialize.CapellaWorkItem = new_work_items[uuid]
#         old_work_item = polarion_wi_map[uuid]
#         if old_work_item.id in back_links:
#             element.create_grouped_back_link_fields(
#                 new_work_item, back_links[old_work_item.id]
#             )

#         api_helper.patch_work_item(
#             api_client,
#             new_work_item,
#             old_work_item,
#             old_work_item.title,
#             "element",
#         )


# def get_types(polarion_type_map, elements) -> set[str]:
#     """Return a set of Polarion types from the current context."""
#     xtypes = set[str]()
#     for obj in chain.from_iterable(elements.values()):
#         xtype = polarion_type_map.get(obj.uuid, type(obj).__name__)
#         xtypes.add(helpers.resolve_element_type(xtype))
#     return xtypes


# def get_elements_and_type_map(
#     config: dict[str, typing.Any],
#     model: capellambse.MelodyModel,
#     diagram_idx: list[dict[str, typing.Any]],
# ) -> tuple[dict[str, list[common.GenericElement]], dict[str, str]]:
#     """Return an elements and UUID to Polarion type map."""

#     def _fix_components(
#         elements: dict[str,
#                     list[common.GenericElement]],
#                     type_map: dict[str, str]
#     ) -> None:
#         for typ, xtype in ACTOR_TYPES.items():
#             if typ not in elements:
#                 continue

#             actors: list[common.GenericElement] = []
#             components: list[common.GenericElement] = []
#             for obj in elements[typ]:
#                 if obj.is_actor:
#                     actors.append(obj)
#                 else:
#                     components.append(obj)
#                     type_map[obj.uuid] = xtype

#             elements[typ] = actors
#             elements[xtype] = components

#         nodes: list[common.GenericElement] = []
#         behaviors: list[common.GenericElement] = []
#         components = []
#         for obj in elements.get("PhysicalComponent", []):
#             if obj.nature is not None and obj.nature.name == "NODE":
#                 nodes.append(obj)
#                 type_map[obj.uuid] = "PhysicalComponentNode"
#             elif obj.nature is not None and obj.nature.name == "BEHAVIOR":
#                 behaviors.append(obj)
#                 type_map[obj.uuid] = "PhysicalComponentBehavior"
#             else:
#                 components.append(obj)

#         if nodes:
#             elements["PhysicalComponentNode"] = nodes
#         if behaviors:
#             elements["PhysicalComponentBehavior"] = behaviors
#         if components:
#             elements["PhysicalComponent"] = components

#     convert_type = POL2CAPELLA_TYPES
#     type_map: dict[str, str] = {}
#     elements: dict[str, list[common.GenericElement]] = {}
#     for _below, pol_types in config.items():
#         below = getattr(model, _below)
#         for typ in pol_types:
#             if isinstance(typ, dict):
#                 typ = list(typ.keys())[0]

#             if typ == "Diagram":
#                 continue

#             xtype = convert_type.get(typ, typ)
#             objects = model.search(xtype, below=below)
#             elements.setdefault(typ, []).extend(objects)
#             for obj in objects:
#                 type_map[obj.uuid] = typ

#     _fix_components(elements, type_map)
#     diagrams_from_cache = {d["uuid"] for d in diagram_idx if d["success"]}
#     elements["Diagram"] = [
#         d for d in model.diagrams if d.uuid in diagrams_from_cache
#     ]
#     for obj in elements["Diagram"]:
#         type_map[obj.uuid] = "Diagram"
#     return elements, type_map
