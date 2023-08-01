# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Objects for synchronization of capella objects to polarion workitems."""

__all__ = [
    "delete_work_items",
    "get_types",
    "get_elements_and_type_map",
    "make_model_elements_index",
    "STATUS_DELETE",
    "UUID_ATTR_NAME",
]

import logging
import pathlib
import typing as t
from itertools import chain

import yaml
from capellambse.model import common

from capella2polarion import polarion_api

logger = logging.getLogger(__name__)

UUID_ATTR_NAME = "uuid_capella"
STATUS_DELETE = "deleted"
ELEMENTS_IDX_PATH = pathlib.Path("elements_index.yaml")
ACTOR_TYPES = {
    "LogicalActor": "LogicalComponent",
    "SystemActor": "SystemComponent",
    "PhysicalActor": "PhysicalComponent",
}
PHYSICAL_COMPONENT_TYPES = {
    "PhysicalComponentNode": "PhysicalComponent",
    "PhysicalComponentBehavior": "PhysicalComponent",
}
POL2CAPELLA_TYPES = (
    {
        "OperationalEntity": "Entity",
        "OperationalInteraction": "FunctionalExchange",
        "SystemCapability": "Capability",
    }
    | ACTOR_TYPES
    | PHYSICAL_COMPONENT_TYPES
)


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
        logger.debug(
            "Delete work item %r...",
            workitem_id := ctx["POLARION_ID_MAP"][uuid],
        )
        return workitem_id

    uuids: set[str] = set(ctx["POLARION_ID_MAP"]) - set(ctx["CAPELLA_UUIDS"])
    work_items = [serialize_for_delete(uuid) for uuid in uuids]
    if work_items:
        try:
            ctx["API"].delete_work_items(work_items)
        except polarion_api.PolarionApiException as error:
            logger.error("Deleting work items failed. %s", error.args[0])


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

            xtype = convert_type.get(typ, typ)
            objects = ctx["MODEL"].search(xtype, below=below)
            elements.setdefault(typ, []).extend(objects)
            for obj in objects:
                type_map[obj.uuid] = typ

    _fix_components(elements, type_map)
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


def make_model_elements_index(ctx: dict[str, t.Any]) -> pathlib.Path:
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
    return ELEMENTS_IDX_PATH


from . import diagram, element, helpers, serialize
