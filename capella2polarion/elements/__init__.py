# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Objects for synchronization of capella objects to polarion workitems."""

from __future__ import annotations

__all__ = [
    "delete_work_items",
    "get_types",
    "get_elements_and_type_map",
    "make_model_elements_index",
    "STATUS_DELETE",
]

import logging
import pathlib
import typing as t
from itertools import chain

import polarion_rest_api_client as polarion_api
import yaml
from capellambse.model import common
from capellambse.model import diagram as diag

logger = logging.getLogger(__name__)

STATUS_DELETE = "deleted"
ELEMENTS_IDX_PATH = pathlib.Path("elements_index.yaml")
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


def get_polarion_wi_map(
    ctx: dict[str, t.Any], type_: str = ""
) -> dict[str, t.Any]:
    """Return a map from Capella UUIDs to Polarion work items."""
    types_ = map(helpers.resolve_element_type, ctx.get("TYPES", []))
    work_item_types = [type_] if type_ else list(types_)
    _type = " ".join(work_item_types)
    work_items = ctx["API"].get_all_work_items(
        f"type:({_type})", {"workitems": "id,uuid_capella,checksum,status"}
    )
    return {
        wi.uuid_capella: wi for wi in work_items if wi.id and wi.uuid_capella
    }


def delete_work_items(ctx: dict[str, t.Any]) -> None:
    """Delete work items in a Polarion project.

    If the delete flag is set to ``False`` in the context work items are
    marked as ``to be deleted`` via the status attribute.

    Parameters
    ----------
    ctx
        The context for the workitem operation to be processed.
    """

    def serialize_for_delete(uuid: str) -> str:
        logger.info(
            "Delete work item %r...",
            workitem_id := ctx["POLARION_ID_MAP"][uuid],
        )
        return workitem_id

    existing_work_items = {
        uuid
        for uuid, work_item in ctx["POLARION_WI_MAP"].items()
        if work_item.status != "deleted"
    }
    uuids: set[str] = existing_work_items - set(ctx["CAPELLA_UUIDS"])
    work_item_ids = [serialize_for_delete(uuid) for uuid in uuids]
    if work_item_ids:
        try:
            ctx["API"].delete_work_items(work_item_ids)
            for uuid in uuids:
                del ctx["POLARION_WI_MAP"][uuid]
                del ctx["POLARION_ID_MAP"][uuid]
        except polarion_api.PolarionApiException as error:
            logger.error("Deleting work items failed. %s", error.args[0])


def post_work_items(ctx: dict[str, t.Any]) -> None:
    """Post work items in a Polarion project.

    Parameters
    ----------
    ctx
        The context for the workitem operation to be processed.
    """
    work_items: list[serialize.CapellaWorkItem] = []
    for work_item in ctx["WORK_ITEMS"].values():
        if work_item.uuid_capella in ctx["POLARION_ID_MAP"]:
            continue

        assert work_item is not None
        work_items.append(work_item)
        logger.info("Create work item for %r...", work_item.title)
    if work_items:
        try:
            ctx["API"].create_work_items(work_items)
            workitems = {wi.uuid_capella: wi for wi in work_items if wi.id}
            ctx["POLARION_WI_MAP"].update(workitems)
            ctx["POLARION_ID_MAP"] = {
                uuid: wi.id for uuid, wi in ctx["POLARION_WI_MAP"].items()
            }
        except polarion_api.PolarionApiException as error:
            logger.error("Creating work items failed. %s", error.args[0])


def patch_work_items(ctx: dict[str, t.Any]) -> None:
    """Update work items in a Polarion project.

    Parameters
    ----------
    ctx
        The context for the workitem operation to be processed.
    """
    ctx["POLARION_ID_MAP"] = uuids = {
        uuid: wi.id
        for uuid, wi in ctx["POLARION_WI_MAP"].items()
        if wi.status == "open" and wi.uuid_capella and wi.id
    }

    back_links: dict[str, list[polarion_api.WorkItemLink]] = {}
    for uuid in uuids:
        objects = ctx["MODEL"]
        if uuid.startswith("_"):
            objects = ctx["MODEL"].diagrams

        obj = objects.by_uuid(uuid)
        work_item: serialize.CapellaWorkItem = ctx["WORK_ITEMS"][uuid]
        old_work_item: serialize.CapellaWorkItem = ctx["POLARION_WI_MAP"][uuid]

        links = element.create_links(obj, ctx)
        work_item.linked_work_items = links
        work_item.id = old_work_item.id

        element.create_grouped_link_fields(work_item, back_links)

    for uuid in uuids:
        new_work_item: serialize.CapellaWorkItem = ctx["WORK_ITEMS"][uuid]
        old_work_item = ctx["POLARION_WI_MAP"][uuid]
        if old_work_item.id in back_links:
            element.create_grouped_back_link_fields(
                new_work_item, back_links[old_work_item.id]
            )

        api_helper.patch_work_item(ctx["API"], new_work_item, old_work_item)


def get_types(ctx: dict[str, t.Any]) -> set[str]:
    """Return a set of Polarion types from the current context."""
    xtypes = set[str]()
    for obj in chain.from_iterable(ctx["ELEMENTS"].values()):
        xtype = ctx["POLARION_TYPE_MAP"].get(obj.uuid, type(obj).__name__)
        xtypes.add(helpers.resolve_element_type(xtype))
    return xtypes


def get_elements_and_type_map(
    ctx: dict[str, t.Any]
) -> tuple[dict[str, list[common.GenericElement]], dict[str, str]]:
    """Return an elements and UUID to Polarion type map."""
    convert_type = POL2CAPELLA_TYPES
    type_map: dict[str, str] = {}
    elements: dict[str, list[common.GenericElement]] = {}
    for _below, pol_types in ctx["CONFIG"].items():
        below = getattr(ctx["MODEL"], _below)
        for typ in pol_types:
            if isinstance(typ, dict):
                typ = list(typ.keys())[0]

            if typ == "Diagram":
                continue

            xtype = convert_type.get(typ, typ)
            objects = ctx["MODEL"].search(xtype, below=below)
            elements.setdefault(typ, []).extend(objects)
            for obj in objects:
                type_map[obj.uuid] = typ

    _fix_components(elements, type_map)
    diagrams_from_cache = {
        d["uuid"] for d in ctx["DIAGRAM_IDX"] if d["success"]
    }
    elements["Diagram"] = [
        d for d in ctx["MODEL"].diagrams if d.uuid in diagrams_from_cache
    ]
    for obj in elements["Diagram"]:
        type_map[obj.uuid] = "Diagram"
    return elements, type_map


def _fix_components(
    elements: dict[str, list[common.GenericElement]], type_map: dict[str, str]
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


def make_model_elements_index(ctx: dict[str, t.Any]) -> None:
    """Create an elements index file for all migrated elements."""
    elements: list[dict[str, t.Any]] = []
    for obj in chain.from_iterable(ctx["ELEMENTS"].values()):
        element_ = {"uuid": obj.uuid, "name": obj.name}
        if pid := ctx["POLARION_ID_MAP"].get(obj.uuid):
            element_["id"] = pid

        for role_id in ctx["ROLES"].get(type(obj).__name__, []):
            attribute = getattr(obj, role_id, None)
            if attribute is None:
                continue
            elif isinstance(attribute, common.ElementList):
                refs = [
                    ctx["POLARION_ID_MAP"].get(a.uuid, a.uuid)
                    for a in attribute
                ]
                if refs:
                    element_[role_id] = refs
            else:
                element_[role_id] = ctx["POLARION_ID_MAP"].get(
                    attribute.uuid, attribute.uuid
                )
        elements.append(element_)

    ELEMENTS_IDX_PATH.write_text(yaml.dump(elements), encoding="utf8")


from . import (  # pylint: disable=cyclic-import
    api_helper,
    element,
    helpers,
    serialize,
)
