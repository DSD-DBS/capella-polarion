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

import functools
import logging
import pathlib
import typing as t
from itertools import chain

import polarion_rest_api_client as polarion_api
import yaml
from capellambse.model import common

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
        logger.debug(
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
    work_items = [serialize_for_delete(uuid) for uuid in uuids]
    if work_items:
        try:
            ctx["API"].delete_work_items(work_items)
        except polarion_api.PolarionApiException as error:
            logger.error("Deleting work items failed. %s", error.args[0])


def create_work_items(ctx: dict[str, t.Any]) -> None:
    """Create work items for a Polarion project.

    Parameters
    ----------
    ctx
        The context for the workitem operation to be processed.
    """
    if work_items := element.create_work_items(ctx):
        try:
            ctx["API"].create_work_items(work_items)
        except polarion_api.PolarionApiException as error:
            logger.error("Creating work items failed. %s", error.args[0])


def update_work_items(ctx: dict[str, t.Any]) -> None:
    """Update work items in a Polarion project.

    Parameters
    ----------
    ctx
        The context for the workitem operation to be processed.
    """

    def prepare_for_update(
        obj: common.GenericElement, ctx: dict[str, t.Any], **kwargs
    ) -> serialize.CapellaWorkItem:
        work_item = serialize.generic_work_item(obj, ctx)
        for key, value in kwargs.items():
            if getattr(work_item, key, None) is None:
                continue

            setattr(work_item, key, value)
        return work_item

    for obj in chain.from_iterable(ctx["ELEMENTS"].values()):
        if obj.uuid not in ctx["POLARION_ID_MAP"]:
            continue

        links = element.create_links(obj, ctx)

        api_helper.patch_work_item(
            ctx,
            ctx["POLARION_ID_MAP"][obj.uuid],
            obj,
            functools.partial(prepare_for_update, links=links),
            obj._short_repr_(),
            "element",
        )


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
    elements["Diagram"] = diagrams = [
        diagram
        for diagram in ctx["MODEL"].diagrams
        if diagram.uuid in ctx["POLARION_ID_MAP"]
    ]
    for diag in diagrams:
        type_map[diag.uuid] = "Diagram"
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
    diagram,
    element,
    helpers,
    serialize,
)
