# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Objects for synchronization of Capella model objects to Polarion."""
from __future__ import annotations

import collections.abc as cabc
import functools
import logging
import pathlib
import types
import typing as t
from collections import defaultdict
from itertools import chain

import polarion_rest_api_client as polarion_api
from capellambse.model import common
from capellambse.model import diagram as diag
from capellambse.model.crosslayer import fa

from capella2polarion.elements import helpers, serialize

logger = logging.getLogger(__name__)

TYPE_RESOLVERS = {"Part": lambda obj: obj.type.uuid}


def create_work_items(
    elements,
    diagram_cache_path: pathlib.Path,
    polarion_type_map,
    polarion_work_item_map,
    model,
    polarion_id_map,
    descr_references,
) -> dict[str, serialize.CapellaWorkItem]:
    """Create a list of work items for Polarion."""
    objects = chain.from_iterable(elements.values())
    _work_items = []
    serializer = serialize.CapellaWorkItemSerializer(
        diagram_cache_path,
        polarion_type_map,
        model,
        polarion_id_map,
        descr_references,
    )
    for obj in objects:
        _work_items.append(serializer.serialize(obj))

    _work_items = list(filter(None, _work_items))
    valid_types = set(map(helpers.resolve_element_type, set(elements)))
    work_items: list[serialize.CapellaWorkItem] = []
    missing_types: set[str] = set()
    for work_item in _work_items:
        assert work_item is not None
        assert work_item.title is not None
        assert work_item.type is not None
        if old := polarion_work_item_map.get(work_item.uuid_capella):
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


def create_links(
    obj: common.GenericElement | diag.Diagram,
    polarion_id_map,
    new_work_items,
    descr_references,
    project_id,
    model,
    roles,
) -> list[polarion_api.WorkItemLink]:
    """Create work item links for a given Capella object."""
    if isinstance(obj, diag.Diagram):
        repres = f"<Diagram {obj.name!r}>"
    else:
        repres = obj._short_repr_()

    workitem = new_work_items[obj.uuid]
    new_links: list[polarion_api.WorkItemLink] = []
    typ = workitem.type[0].upper() + workitem.type[1:]
    for role_id in roles.get(typ, []):
        if role_id == "description_reference":
            new_links.extend(
                _handle_description_reference_links(
                    polarion_id_map,
                    descr_references,
                    project_id,
                    model,
                    obj,
                    role_id,
                    {},
                )
            )
        elif role_id == "diagram_elements":
            new_links.extend(
                _handle_diagram_reference_links(
                    polarion_id_map, model, project_id, obj, role_id, {}
                )
            )
        elif role_id == "input_exchanges":
            new_links.extend(
                _handle_exchanges(
                    polarion_id_map,
                    model,
                    project_id,
                    obj,
                    role_id,
                    {},
                    "inputs",
                )
            )
        elif role_id == "output_exchanges":
            new_links.extend(
                _handle_exchanges(
                    polarion_id_map,
                    model,
                    project_id,
                    obj,
                    role_id,
                    {},
                    "outputs",
                )
            )
        else:
            if (refs := getattr(obj, role_id, None)) is None:
                logger.info(
                    "Unable to create work item link %r for [%s]. "
                    "There is no %r attribute on %s",
                    role_id,
                    workitem.id,
                    role_id,
                    repres,
                )
                continue

            if isinstance(refs, common.ElementList):
                new: cabc.Iterable[str] = refs.by_uuid  # type: ignore[assignment]
            else:
                assert hasattr(refs, "uuid")
                new = [refs.uuid]

            new = set(
                _get_work_item_ids(polarion_id_map, model, workitem.id, new, role_id)
            )
            new_links.extend(_create(project_id, workitem.id, role_id, new, {}))
    return new_links


def _get_work_item_ids(
    polarion_id_map,
    model,
    primary_id: str,
    uuids: cabc.Iterable[str],
    role_id: str,
) -> cabc.Iterator[str]:
    for uuid in uuids:
        if wid := polarion_id_map.get(uuid):
            yield wid
        else:
            obj = model.by_uuid(uuid)
            logger.info(
                "Unable to create work item link %r for [%s]. "
                "Couldn't identify work item for %r",
                role_id,
                primary_id,
                obj._short_repr_(),
            )


def _handle_description_reference_links(
    polarion_id_map,
    descr_references,
    project_id,
    model,
    obj: common.GenericElement,
    role_id: str,
    links: dict[str, polarion_api.WorkItemLink],
) -> list[polarion_api.WorkItemLink]:
    refs = descr_references.get(obj.uuid, [])
    wid = polarion_id_map[obj.uuid]
    refs = set(_get_work_item_ids(polarion_id_map, model, wid, refs, role_id))
    return _create(project_id, wid, role_id, refs, links)


def _handle_diagram_reference_links(
    polarion_id_map,
    model,
    project_id,
    obj: diag.Diagram,
    role_id: str,
    links: dict[str, polarion_api.WorkItemLink],
) -> list[polarion_api.WorkItemLink]:
    try:
        refs = set(_collect_uuids(obj.nodes))
        wid = polarion_id_map[obj.uuid]
        refs = set(
            _get_work_item_ids(polarion_id_map, model, wid, refs, role_id)
        )
        ref_links = _create(project_id, wid, role_id, refs, links)
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
    project_id,
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
            secondary_work_item_project=project_id,
        )
        for id in new
    ]
    return list(filter(None, _new_links))


def _handle_exchanges(
    polarion_id_map,
    model,
    project_id,
    obj: fa.Function,
    role_id: str,
    links: dict[str, polarion_api.WorkItemLink],
    attr: str = "inputs",
) -> list[polarion_api.WorkItemLink]:
    wid = polarion_id_map[obj.uuid]
    exchanges: list[str] = []
    for element in getattr(obj, attr):
        uuids = element.exchanges.by_uuid
        exs = _get_work_item_ids(polarion_id_map, model, wid, uuids, role_id)
        exchanges.extend(set(exs))
    return _create(project_id, wid, role_id, exchanges, links)


def create_grouped_link_fields(
    work_item: serialize.CapellaWorkItem,
    back_links: dict[str, list[polarion_api.WorkItemLink]] | None = None,
):
    """Create the grouped link work items fields from the primary work item.

    Parameters
    ----------
    work_item
        WorkItem to create the fields for.
    back_links
        A dictionary of secondary WorkItem IDs to links to create
        backlinks later.
    """
    wi = f"[{work_item.id}]({work_item.type} {work_item.title})"
    logger.debug("Building grouped links for work item %r...", wi)
    for role, grouped_links in _group_by(
        "role", work_item.linked_work_items
    ).items():
        if back_links is not None:
            for link in grouped_links:
                key = link.secondary_work_item_id
                back_links.setdefault(key, []).append(link)

        _create_link_fields(work_item, role, grouped_links)


def create_grouped_back_link_fields(
    work_item: serialize.CapellaWorkItem,
    links: list[polarion_api.WorkItemLink],
):
    """Create backlinks for the given WorkItem using a list of backlinks.

    Parameters
    ----------
    work_item
        WorkItem to create the fields for
    links
        List of links referencing work_item as secondary
    """
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

    urls.sort()
    url_list = "\n".join(urls)
    return f"<ul>{url_list}</ul>"


def _create_link_fields(
    work_item: serialize.CapellaWorkItem,
    role: str,
    links: list[polarion_api.WorkItemLink],
    reverse: bool = False,
):
    role = f"{role}_reverse" if reverse else role
    work_item.additional_attributes[role] = {
        "type": "text/html",
        "value": _make_url_list(links, reverse),
    }
