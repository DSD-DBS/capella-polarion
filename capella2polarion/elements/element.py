# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Objects for synchronization of Capella model objects to Polarion."""
from __future__ import annotations

import collections.abc as cabc
import logging
import typing as t
from itertools import chain

from capellambse.model import common

from capella2polarion import polarion_api
from capella2polarion.elements import *
from capella2polarion.elements import serialize

logger = logging.getLogger(__name__)

TYPE_RESOLVERS = {"Part": lambda obj: obj.type.uuid}


def create_work_items(ctx: dict[str, t.Any]) -> None:
    """Create a set of work items in Polarion."""

    def serialize_for_create(
        obj: common.GenericElement,
    ) -> polarion_api.WorkItem | None:
        logger.debug(
            "Create work item for model element %r...", obj._short_repr_()
        )
        attributes = serialize.element(obj, ctx, serialize.generic_attributes)
        if attributes is None:
            return None
        return polarion_api.WorkItem(**attributes)

    objects = chain.from_iterable(ctx["ELEMENTS"].values())
    work_items = [
        serialize_for_create(obj)
        for obj in objects
        if obj.uuid not in ctx["POLARION_ID_MAP"]
    ]
    work_items = list(filter(None.__ne__, work_items))
    if work_items:
        try:
            ctx["API"].create_work_items(work_items)
        except polarion_api.PolarionApiException as error:
            logger.error("Creating work items failed. %s", error.args[0])


def update_work_items(ctx: dict[str, t.Any]) -> None:
    """Update a set of work items in Polarion."""
    for obj in chain.from_iterable(ctx["ELEMENTS"].values()):
        if obj.uuid not in ctx["POLARION_ID_MAP"]:
            continue

        logger.debug(
            "Update work item %r for model element %r...",
            wid := ctx["POLARION_ID_MAP"][obj.uuid],
            obj._short_repr_(),
        )
        attributes = serialize.element(obj, ctx, serialize.generic_attributes)
        if attributes is None:
            continue

        del attributes["type"]
        del attributes["uuid_capella"]
        attributes["status"] = "open"
        try:
            ctx["API"].update_work_item(
                polarion_api.WorkItem(id=wid, **attributes)
            )
        except polarion_api.PolarionApiException as error:
            wi = f"{wid}({obj._short_repr_()})"
            logger.error("Updating work item %r failed. %s", wi, error.args[0])


class LinkBuilder(t.NamedTuple):
    """Helper class for creating workitem links."""

    context: dict[str, t.Any]
    obj: common.GenericElement

    def create(
        self, secondary_id: str, role_id: str
    ) -> polarion_api.WorkItemLink | None:
        """Post a work item link create request."""
        primary_id = self.context["POLARION_ID_MAP"][self.obj.uuid]
        logger.debug(
            "Create work item link %r from %r to %r for model element %r",
            role_id,
            primary_id,
            secondary_id,
            self.obj._short_repr_(),
        )
        return polarion_api.WorkItemLink(
            primary_id,
            secondary_id,
            role_id,
            secondary_work_item_project=self.context["PROJECT_ID"],
        )


def update_links(
    ctx: dict[str, t.Any],
    elements: cabc.Iterable[common.GenericElement] | None = None,
) -> None:
    """Create and update work item links in Polarion."""
    custom_link_resolvers = CUSTOM_LINKS
    for elt in elements or chain.from_iterable(ctx["ELEMENTS"].values()):
        if elt.uuid not in ctx["POLARION_ID_MAP"]:
            continue

        workitem_id = ctx["POLARION_ID_MAP"][elt.uuid]
        logger.debug(
            "Fetching links for work item %r(%r)...",
            workitem_id,
            elt._short_repr_(),
        )
        links: list[polarion_api.WorkItemLink]
        try:
            links = ctx["API"].get_all_work_item_links(workitem_id)
        except polarion_api.PolarionApiException as error:
            logger.error(
                "Fetching links for work item %r(%r). failed %s",
                workitem_id,
                elt._short_repr_(),
                error.args[0],
            )
            continue

        link_builder = LinkBuilder(ctx, elt)
        for role_id in ctx["ROLES"].get(type(elt).__name__, []):
            id_link_map: dict[str, polarion_api.WorkItemLink] = {}
            for link in links:
                if role_id != link.role:
                    continue

                id_link_map[link.secondary_work_item_id] = link

            if resolver := custom_link_resolvers.get(role_id):
                resolver(link_builder, role_id, id_link_map)
                continue

            if (refs := getattr(elt, role_id, None)) is None:
                continue

            if isinstance(refs, common.ElementList):
                new = refs.by_uuid
            else:
                assert hasattr(refs, "uuid")
                new = [refs.uuid]

            new = set(_get_work_item_ids(ctx, new, role_id))
            _handle_create_and_delete(
                link_builder, role_id, new, id_link_map, id_link_map
            )


def _get_work_item_ids(
    ctx: dict[str, t.Any], uuids: cabc.Iterable[str], role_id: str
) -> cabc.Iterator[str]:
    for uuid in uuids:
        if wid := ctx["POLARION_ID_MAP"].get(uuid):
            yield wid
        else:
            obj = ctx["MODEL"].by_uuid(uuid)
            logger.debug(
                "Unable to create work item link %r. "
                "Couldn't identify work item for %r",
                role_id,
                obj._short_repr_(),
            )


def _handle_description_reference_links(
    link_builder: LinkBuilder,
    role_id: str,
    links: dict[str, polarion_api.WorkItemLink],
) -> None:
    refs = link_builder.context["DESCR_REFERENCES"].get(link_builder.obj.uuid)
    refs = set(_get_work_item_ids(link_builder.context, refs, role_id))
    _handle_create_and_delete(link_builder, role_id, refs, links, links)


def _handle_diagram_reference_links(
    link_builder: LinkBuilder,
    role_id: str,
    links: dict[str, polarion_api.WorkItemLink],
) -> None:
    try:
        refs = set(_collect_uuids(link_builder.obj.nodes))
        refs = set(_get_work_item_ids(link_builder.context, refs, role_id))
        _handle_create_and_delete(link_builder, role_id, refs, links, links)
    except StopIteration:
        logger.exception(
            "Could not create links for diagram %r",
            link_builder.obj._short_repr_(),
        )


def _collect_uuids(nodes: list[common.GenericElement]) -> cabc.Iterator[str]:
    type_resolvers = TYPE_RESOLVERS
    for node in nodes:
        uuid = node.uuid
        if resolver := type_resolvers.get(type(node).__name__):
            uuid = resolver(node)

        yield uuid


def _handle_create_and_delete(
    link_builder: LinkBuilder,
    role_id: str,
    new: cabc.Iterable[str],
    old: cabc.Iterable[str],
    links: dict[str, t.Any],
) -> None:
    create = set(new) - set(old)
    new_links = [link_builder.create(id, role_id) for id in create]
    new_links = list(filter(None.__ne__, new_links))
    if new_links:
        link_builder.context["API"].create_work_item_links(new_links)

    delete = set(old) - set(new)
    dead_links = [links.get(id) for id in delete]
    dead_links = list(filter(None.__ne__, dead_links))
    for link in dead_links:
        rep = link_builder.obj._short_repr_()
        logger.debug(
            "Delete work item link %r for model element %r", link, rep
        )
    if dead_links:
        link_builder.context["API"].delete_work_item_links(dead_links)


CUSTOM_LINKS = {
    "description_reference": _handle_description_reference_links,
    "diagram_elements": _handle_diagram_reference_links,
}
