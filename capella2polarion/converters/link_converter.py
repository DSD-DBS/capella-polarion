# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Objects for synchronization of Capella model objects to Polarion."""
from __future__ import annotations

import collections.abc as cabc
import functools
import logging
import typing as t
from collections import defaultdict

import capellambse
import polarion_rest_api_client as polarion_api
from capellambse.model import common
from capellambse.model import diagram as diag
from capellambse.model.crosslayer import fa

from capella2polarion import data_models
from capella2polarion.connectors import polarion_repo
from capella2polarion.converters import element_converter

logger = logging.getLogger(__name__)

TYPE_RESOLVERS = {"Part": lambda obj: obj.type.uuid}


class LinkSerializer:
    """A converter for capella element links and description references."""

    def __init__(
        self,
        capella_polarion_mapping: polarion_repo.PolarionDataRepository,
        new_work_items: dict[str, data_models.CapellaWorkItem],
        description_references: dict[str, list[str]],
        project_id: str,
        model: capellambse.MelodyModel,
    ):
        self.capella_polarion_mapping = capella_polarion_mapping
        self.new_work_items = new_work_items
        self.description_references = description_references
        self.project_id = project_id
        self.model = model

        self.serializers: dict[
            str,
            cabc.Callable[
                [common.GenericElement, str, str, dict[str, t.Any]],
                list[polarion_api.WorkItemLink],
            ],
        ] = {
            "description_reference": self._handle_description_reference_links,
            "diagram_elements": self._handle_diagram_reference_links,
            "input_exchanges": functools.partial(
                self._handle_exchanges, attr="inputs"
            ),
            "output_exchanges": functools.partial(
                self._handle_exchanges, attr="outputs"
            ),
        }

    def create_links_for_work_item(
        self,
        obj: common.GenericElement | diag.Diagram,
        roles,
    ) -> list[polarion_api.WorkItemLink]:
        """Create work item links for a given Capella object."""
        if isinstance(obj, diag.Diagram):
            repres = f"<Diagram {obj.name!r}>"
        else:
            repres = obj._short_repr_()

        work_item = self.new_work_items[obj.uuid]
        new_links: list[polarion_api.WorkItemLink] = []
        typ = work_item.type[0].upper() + work_item.type[1:]
        for role_id in roles.get(typ, []):
            if serializer := self.serializers.get(role_id):
                new_links.extend(serializer(obj, work_item.id, role_id, {}))
            else:
                if (refs := getattr(obj, role_id, None)) is None:
                    logger.info(
                        "Unable to create work item link %r for [%s]. "
                        "There is no %r attribute on %s",
                        role_id,
                        work_item.id,
                        role_id,
                        repres,
                    )
                    continue

                if isinstance(refs, common.ElementList):
                    new: cabc.Iterable[str] = refs.by_uuid  # type: ignore[assignment]
                else:
                    assert hasattr(refs, "uuid")
                    new = [refs.uuid]

                new = set(self._get_work_item_ids(work_item.id, new, role_id))
                new_links.extend(self._create(work_item.id, role_id, new, {}))
        return new_links

    def _get_work_item_ids(
        self,
        primary_id: str,
        uuids: cabc.Iterable[str],
        role_id: str,
    ) -> cabc.Iterator[str]:
        for uuid in uuids:
            if wid := self.capella_polarion_mapping.get_work_item_id(uuid):
                yield wid
            else:
                obj = self.model.by_uuid(uuid)
                logger.info(
                    "Unable to create work item link %r for [%s]. "
                    "Couldn't identify work item for %r",
                    role_id,
                    primary_id,
                    obj._short_repr_(),
                )

    def _handle_description_reference_links(
        self,
        obj: common.GenericElement,
        work_item_id: str,
        role_id: str,
        links: dict[str, polarion_api.WorkItemLink],
    ) -> list[polarion_api.WorkItemLink]:
        refs = self.description_references.get(obj.uuid, [])
        ref_set = set(self._get_work_item_ids(work_item_id, refs, role_id))
        return self._create(work_item_id, role_id, ref_set, links)

    def _handle_diagram_reference_links(
        self,
        obj: diag.Diagram,
        work_item_id: str,
        role_id: str,
        links: dict[str, polarion_api.WorkItemLink],
    ) -> list[polarion_api.WorkItemLink]:
        try:
            refs = set(self._collect_uuids(obj.nodes))
            refs = set(self._get_work_item_ids(work_item_id, refs, role_id))
            ref_links = self._create(work_item_id, role_id, refs, links)
        except StopIteration:
            logger.exception(
                "Could not create links for diagram %r", obj._short_repr_()
            )
            ref_links = []
        return ref_links

    def _collect_uuids(
        self,
        nodes: cabc.Iterable[common.GenericElement],
    ) -> cabc.Iterator[str]:
        type_resolvers = TYPE_RESOLVERS
        for node in nodes:
            uuid = node.uuid
            if resolver := type_resolvers.get(type(node).__name__):
                uuid = resolver(node)

            yield uuid

    def _create(
        self,
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
                secondary_work_item_project=self.project_id,
            )
            for id in new
        ]
        return list(filter(None, _new_links))

    def _handle_exchanges(
        self,
        obj: fa.Function,
        work_item_id: str,
        role_id: str,
        links: dict[str, polarion_api.WorkItemLink],
        attr: str = "inputs",
    ) -> list[polarion_api.WorkItemLink]:
        exchanges: list[str] = []
        for element in getattr(obj, attr):
            uuids = element.exchanges.by_uuid
            exs = self._get_work_item_ids(work_item_id, uuids, role_id)
            exchanges.extend(set(exs))
        return self._create(work_item_id, role_id, exchanges, links)


def create_grouped_link_fields(
    work_item: data_models.CapellaWorkItem,
    back_links: dict[str, list[polarion_api.WorkItemLink]] | None = None,
):
    """Create the grouped link fields from the primary work item.

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
    work_item: data_models.CapellaWorkItem,
    links: list[polarion_api.WorkItemLink],
):
    """Create fields for the given WorkItem using a list of backlinks.

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

        url = element_converter.POLARION_WORK_ITEM_URL.format(pid=pid)
        urls.append(f"<li>{url}</li>")

    urls.sort()
    url_list = "\n".join(urls)
    return f"<ul>{url_list}</ul>"


def _create_link_fields(
    work_item: data_models.CapellaWorkItem,
    role: str,
    links: list[polarion_api.WorkItemLink],
    reverse: bool = False,
):
    role = f"{role}_reverse" if reverse else role
    work_item.additional_attributes[role] = {
        "type": "text/html",
        "value": _make_url_list(links, reverse),
    }
