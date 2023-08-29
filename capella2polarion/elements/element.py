# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Objects for synchronization of Capella model objects to Polarion."""
from __future__ import annotations

import collections.abc as cabc
import logging
import typing as t
from itertools import chain

import polarion_rest_api_client as polarion_api
from capellambse.model import common

from capella2polarion import elements
from capella2polarion.elements import serialize

logger = logging.getLogger(__name__)

TYPE_RESOLVERS = {"Part": lambda obj: obj.type.uuid}
TYPES_POL2CAPELLA = {
    ctype: ptype for ptype, ctype in elements.POL2CAPELLA_TYPES.items()
}


def create_work_items(
    ctx: dict[str, t.Any],
    objects: cabc.Iterable[common.GenericElement] | None = None,
) -> list[common.GenericElement]:
    """Create a set of work items in Polarion."""

    def serialize_for_create(
        obj: common.GenericElement,
    ) -> serialize.CapellaWorkItem | None:
        logger.debug(
            "Create work item for model element %r...", obj._short_repr_()
        )
        return serialize.element(obj, ctx, serialize.generic_work_item)

    objects = objects or chain.from_iterable(ctx["ELEMENTS"].values())
    work_items = [
        serialize_for_create(obj)
        for obj in objects
        if obj.uuid not in ctx["POLARION_ID_MAP"]
    ]
    return list(filter(None.__ne__, work_items))


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


def create_links(
    obj: common.GenericElement, ctx: dict[str, t.Any]
) -> list[polarion_api.WorkItemLink]:
    """Create work item links in Polarion."""
    custom_link_resolvers = CUSTOM_LINKS
    reverse_type_map = TYPES_POL2CAPELLA
    link_builder = LinkBuilder(ctx, obj)
    ptype = reverse_type_map.get(type(obj).__name__, type(obj).__name__)
    new_links: list[polarion_api.WorkItemLink] = []
    for role_id in ctx["ROLES"].get(ptype, []):
        if resolver := custom_link_resolvers.get(role_id):
            new_links.extend(resolver(link_builder, role_id, {}))
            continue

        if (refs := getattr(obj, role_id, None)) is None:
            continue

        if isinstance(refs, common.ElementList):
            new = refs.by_uuid
        else:
            assert hasattr(refs, "uuid")
            new = [refs.uuid]

        new_links.extend(_create(link_builder, role_id, new, {}))
    return new_links


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
) -> list[polarion_api.WorkItemLink]:
    refs = link_builder.context["DESCR_REFERENCES"].get(link_builder.obj.uuid)
    refs = set(_get_work_item_ids(link_builder.context, refs, role_id))
    return _create(link_builder, role_id, refs, links)


def _handle_diagram_reference_links(
    link_builder: LinkBuilder,
    role_id: str,
    links: dict[str, polarion_api.WorkItemLink],
) -> list[polarion_api.WorkItemLink]:
    try:
        refs = set(_collect_uuids(link_builder.obj.nodes))
        refs = set(_get_work_item_ids(link_builder.context, refs, role_id))
        ref_links = _create(link_builder, role_id, refs, links)
    except StopIteration:
        logger.exception(
            "Could not create links for diagram %r",
            link_builder.obj._short_repr_(),
        )
        ref_links = []
    return ref_links


def _collect_uuids(nodes: list[common.GenericElement]) -> cabc.Iterator[str]:
    type_resolvers = TYPE_RESOLVERS
    for node in nodes:
        uuid = node.uuid
        if resolver := type_resolvers.get(type(node).__name__):
            uuid = resolver(node)

        yield uuid


def _create(
    link_builder: LinkBuilder,
    role_id: str,
    new: cabc.Iterable[str],
    old: cabc.Iterable[str],
) -> list[polarion_api.WorkItemLink]:
    new = set(new) - set(old)
    new = set(_get_work_item_ids(link_builder.context, new, role_id))
    _new_links = [link_builder.create(id, role_id) for id in new]
    return list(filter(None.__ne__, _new_links))


CUSTOM_LINKS = {
    "description_reference": _handle_description_reference_links,
    "diagram_elements": _handle_diagram_reference_links,
}
