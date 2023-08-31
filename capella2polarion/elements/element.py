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
from capellambse.model import diagram as diag

from capella2polarion import elements
from capella2polarion.elements import serialize

logger = logging.getLogger(__name__)

TYPE_RESOLVERS = {"Part": lambda obj: obj.type.uuid}
TYPES_POL2CAPELLA = {
    ctype: ptype for ptype, ctype in elements.POL2CAPELLA_TYPES.items()
}


def create_work_items(
    ctx: dict[str, t.Any]
) -> list[serialize.CapellaWorkItem]:
    """Create a set of work items in Polarion."""
    objects = chain.from_iterable(ctx["ELEMENTS"].values())
    work_items = [
        serialize.element(obj, ctx, serialize.generic_work_item)
        for obj in objects
    ]
    return list(filter(None.__ne__, work_items))  # type: ignore[arg-type]


def create_links(
    obj: common.GenericElement | diag.Diagram, ctx: dict[str, t.Any]
) -> list[polarion_api.WorkItemLink]:
    """Create work item links for a given Capella object."""
    custom_link_resolvers = CUSTOM_LINKS
    reverse_type_map = TYPES_POL2CAPELLA
    if isinstance(obj, diag.Diagram):
        repres = f"<Diagram {obj.name!r}>"
    else:
        repres = obj._short_repr_()

    wid = ctx["POLARION_ID_MAP"][obj.uuid]
    ptype = reverse_type_map.get(type(obj).__name__, type(obj).__name__)
    new_links: list[polarion_api.WorkItemLink] = []
    for role_id in ctx["ROLES"].get(ptype, []):
        if resolver := custom_link_resolvers.get(role_id):
            new_links.extend(resolver(ctx, obj, role_id, {}))
            continue

        if (refs := getattr(obj, role_id, None)) is None:
            logger.info(
                "Unable to create work item link %r for [%s]. "
                "There is no %r attribute on %s",
                role_id,
                wid,
                role_id,
                repres,
            )
            continue

        if isinstance(refs, common.ElementList):
            new = refs.by_uuid
        else:
            assert hasattr(refs, "uuid")
            new = [refs.uuid]

        new = set(_get_work_item_ids(ctx, wid, new, role_id))
        new_links.extend(_create(ctx, wid, role_id, new, {}))
    return new_links


def _get_work_item_ids(
    ctx: dict[str, t.Any],
    primary_id: str,
    uuids: cabc.Iterable[str],
    role_id: str,
) -> cabc.Iterator[str]:
    for uuid in uuids:
        if wid := ctx["POLARION_ID_MAP"].get(uuid):
            yield wid
        else:
            obj = ctx["MODEL"].by_uuid(uuid)
            logger.info(
                "Unable to create work item link %r for [%s]. "
                "Couldn't identify work item for %r",
                role_id,
                primary_id,
                obj._short_repr_(),
            )


def _handle_description_reference_links(
    context: dict[str, t.Any],
    obj: common.GenericElement,
    role_id: str,
    links: dict[str, polarion_api.WorkItemLink],
) -> list[polarion_api.WorkItemLink]:
    refs = context["DESCR_REFERENCES"].get(obj.uuid)
    wid = context["POLARION_ID_MAP"][obj.uuid]
    refs = set(_get_work_item_ids(context, wid, refs, role_id))
    return _create(context, wid, role_id, refs, links)


def _handle_diagram_reference_links(
    context: dict[str, t.Any],
    obj: diag.Diagram,
    role_id: str,
    links: dict[str, polarion_api.WorkItemLink],
) -> list[polarion_api.WorkItemLink]:
    try:
        refs = set(_collect_uuids(obj.nodes))
        wid = context["POLARION_ID_MAP"][obj.uuid]
        refs = set(_get_work_item_ids(context, wid, refs, role_id))
        ref_links = _create(context, wid, role_id, refs, links)
    except StopIteration:
        logger.exception(
            "Could not create links for diagram %r", obj._short_repr_()
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
    context: dict[str, t.Any],
    primary_id: str,
    role_id: str,
    new: cabc.Iterable[str],
    old: cabc.Iterable[str],
) -> list[polarion_api.WorkItemLink]:
    new = set(new) - set(old)
    _new_links = [
        polarion_api.WorkItemLink(
            primary_id,
            id,
            role_id,
            secondary_work_item_project=context["PROJECT_ID"],
        )
        for id in new
    ]
    return list(filter(None.__ne__, _new_links))


CUSTOM_LINKS = {
    "description_reference": _handle_description_reference_links,
    "diagram_elements": _handle_diagram_reference_links,
}
