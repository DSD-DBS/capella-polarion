# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Objects for synchronization of Capella model objects to Polarion."""
from __future__ import annotations

import collections.abc as cabc
import functools
import logging
import typing as t
from collections import defaultdict
from itertools import chain

import polarion_rest_api_client as polarion_api
from capellambse.model import common
from capellambse.model import diagram as diag
from capellambse.model.crosslayer import fa

from capella2polarion import elements
from capella2polarion.elements import helpers, serialize

logger = logging.getLogger(__name__)

TYPE_RESOLVERS = {"Part": lambda obj: obj.type.uuid}
TYPES_POL2CAPELLA = {
    ctype: ptype for ptype, ctype in elements.POL2CAPELLA_TYPES.items()
}


def create_work_items(
    ctx: dict[str, t.Any]
) -> list[serialize.CapellaWorkItem]:
    """Create a list of work items for Polarion."""
    objects = chain.from_iterable(ctx["ELEMENTS"].values())
    _work_items = []
    serializer: cabc.Callable[
        [diag.Diagram | common.GenericElement, dict[str, t.Any]],
        serialize.CapellaWorkItem,
    ]
    for obj in objects:
        if isinstance(obj, diag.Diagram):
            serializer = serialize.diagram
        else:
            serializer = serialize.generic_work_item

        _work_items.append(serialize.element(obj, ctx, serializer))

    _work_items = list(filter(None, _work_items))
    valid_types = set(map(helpers.resolve_element_type, set(ctx["ELEMENTS"])))
    work_items: list[serialize.CapellaWorkItem] = []
    missing_types: set[str] = set()
    for work_item in _work_items:
        assert work_item is not None
        if work_item.type in valid_types:
            work_items.append(work_item)
        else:
            missing_types.add(work_item.type)

    if missing_types:
        logger.debug(
            "%r are missing in the capella2polarion configuration",
            ", ".join(missing_types),
        )
    ctx["WORK_ITEMS"] = {wi.uuid_capella: wi for wi in work_items}
    return work_items


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
            new: cabc.Iterable[str] = refs.by_uuid  # type: ignore[assignment]
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
    refs = context["DESCR_REFERENCES"].get(obj.uuid, [])
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


def _collect_uuids(
    nodes: cabc.Iterable[common.GenericElement],
) -> cabc.Iterator[str]:
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
    return list(filter(None, _new_links))


def _handle_exchanges(
    context: dict[str, t.Any],
    obj: fa.Function,
    role_id: str,
    links: dict[str, polarion_api.WorkItemLink],
    attr: str = "inputs",
) -> list[polarion_api.WorkItemLink]:
    wid = context["POLARION_ID_MAP"][obj.uuid]
    exchanges: list[str] = []
    for element in getattr(obj, attr):
        uuids = element.exchanges.by_uuid
        exs = _get_work_item_ids(context, wid, uuids, role_id)
        exchanges.extend(set(exs))
    return _create(context, wid, role_id, exchanges, links)


def maintain_grouped_links_attributes(
    work_item_map: dict[str, serialize.CapellaWorkItem],
    polarion_id_map: dict[str, str],
    include_back_links,
) -> None:
    """Create list attributes for links of all work items.

    The list is updated on all primary work items and reverse links can
    be added, too.
    """
    back_links: dict[str, list[polarion_api.WorkItemLink]] = {}
    reverse_polarion_id_map = {v: k for k, v in polarion_id_map.items()}

    def _create_link_fields(
        work_item: serialize.CapellaWorkItem,
        role: str,
        links: list[polarion_api.WorkItemLink],
        reverse: bool = False,
    ):
        # TODO check why we only create links for > 2 per role
        if len(links) < 2:
            return
        role = f"{role}_reverse" if reverse else role
        work_item.additional_attributes[role] = {
            "type": "text/html",
            "value": _make_url_list(links, reverse),
        }

    for work_item in work_item_map.values():
        wi = f"[{work_item.id}]({work_item.type} {work_item.title})"
        logger.debug("Building grouped links for work item %r...", wi)

        for role, grouped_links in _group_by(
            "role", work_item.linked_work_items
        ).items():
            if include_back_links:
                for link in grouped_links:
                    uuid = reverse_polarion_id_map[link.secondary_work_item_id]
                    if uuid not in back_links:
                        back_links[uuid] = []
                    back_links[uuid].append(link)

            _create_link_fields(work_item, role, grouped_links)

    if include_back_links:
        for uuid, links in back_links.items():
            work_item = work_item_map[uuid]
            for role, grouped_links in _group_by("role", links).items():
                _create_link_fields(work_item, role, grouped_links, True)


def _group_by(
    attr: str,
    links: cabc.Iterable[polarion_api.WorkItemLink],
) -> dict[str, list[polarion_api.WorkItemLink]]:
    group = defaultdict(list)
    for link in links:
        key = getattr(link, attr)
        group[key].append(link)
    return group


def _make_url_list(
    links: cabc.Iterable[polarion_api.WorkItemLink], reverse: bool = False
) -> str:
    urls: list[str] = []
    for link in links:
        if reverse:
            pid = link.primary_work_item_id
        else:
            pid = link.secondary_work_item_id

        url = serialize.POLARION_WORK_ITEM_URL.format(pid=pid)
        urls.append(f"<li>{url}</li>")
    url_list = "\n".join(urls)
    return f"<ul>{url_list}</ul>"


CustomLinkMaker = cabc.Callable[
    [
        dict[str, t.Any],
        diag.Diagram | common.GenericElement,
        str,
        dict[str, t.Any],
    ],
    list[polarion_api.WorkItemLink],
]
CUSTOM_LINKS: dict[str, CustomLinkMaker] = {
    "description_reference": _handle_description_reference_links,
    "diagram_elements": _handle_diagram_reference_links,
    "input_exchanges": functools.partial(_handle_exchanges, attr="inputs"),
    "output_exchanges": functools.partial(_handle_exchanges, attr="outputs"),
}
