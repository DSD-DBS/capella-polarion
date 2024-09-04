# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Objects for synchronization of Capella model objects to Polarion."""
from __future__ import annotations

import collections.abc as cabc
import logging
import typing as t
from collections import defaultdict

import capellambse
import polarion_rest_api_client as polarion_api
from capellambse.model import common
from capellambse.model import diagram as diag

from capella2polarion import data_models
from capella2polarion.connectors import polarion_repo
from capella2polarion.converters import (
    converter_config,
    data_session,
    polarion_html_helper,
)

logger = logging.getLogger(__name__)

TYPE_RESOLVERS = {"Part": lambda obj: obj.type.uuid}
_Serializer: t.TypeAlias = cabc.Callable[
    [common.GenericElement, str, str, dict[str, t.Any]],
    list[polarion_api.WorkItemLink],
]


class LinkSerializer:
    """A converter for capella element links and description references."""

    def __init__(
        self,
        capella_polarion_mapping: polarion_repo.PolarionDataRepository,
        converter_session: data_session.ConverterSession,
        project_id: str,
        model: capellambse.MelodyModel,
    ):
        self.capella_polarion_mapping = capella_polarion_mapping
        self.converter_session = converter_session
        self.project_id = project_id
        self.model = model

        self.serializers: dict[str, _Serializer] = {
            converter_config.DESCRIPTION_REFERENCE_SERIALIZER: self._handle_description_reference_links,  # pylint: disable=line-too-long
            converter_config.DIAGRAM_ELEMENTS_SERIALIZER: self._handle_diagram_reference_links,  # pylint: disable=line-too-long
        }

    def create_links_for_work_item(
        self, uuid: str
    ) -> list[polarion_api.WorkItemLink]:
        """Create work item links for a given Capella object."""
        converter_data = self.converter_session[uuid]
        obj = converter_data.capella_element
        work_item = converter_data.work_item
        assert work_item is not None
        assert work_item.id is not None
        new_links: list[polarion_api.WorkItemLink] = []
        link_errors: list[str] = []
        for link_config in converter_data.type_config.links:
            serializer = self.serializers.get(link_config.capella_attr)
            role_id = link_config.polarion_role
            try:
                if serializer:
                    new_links.extend(
                        serializer(obj, work_item.id, role_id, {})
                    )
                else:
                    refs = _resolve_attribute(obj, link_config.capella_attr)
                    new: cabc.Iterable[str]
                    if isinstance(refs, common.ElementList):
                        new = refs.by_uuid  # type: ignore[assignment]
                    else:
                        assert hasattr(refs, "uuid"), "No 'uuid' on value"
                        new = [refs.uuid]

                    new = set(
                        self._get_work_item_ids(work_item.id, new, role_id)
                    )
                    new_links.extend(
                        self._create(work_item.id, role_id, new, {})
                    )
            except Exception as error:
                error_text = f"{type(error).__name__} {str(error)}"
                link_errors.extend(
                    [
                        f"Requested attribute: {link_config.capella_attr}",
                        error_text,
                        "--------",
                    ]
                )

        if link_errors:
            for link_error in link_errors:
                converter_data.errors.add(link_error)

            log_args = (
                converter_data.capella_element._short_repr_(),
                "\n\t".join(link_errors),
            )
            if not new_links:
                logger.error("Link creation for %r failed:\n\t%s", *log_args)
            else:
                logger.warning(
                    "Link creation for %r partially successful. Some links "
                    "were not created:"
                    "\n\t%s",
                    *log_args,
                )

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
        refs = self.converter_session[obj.uuid].description_references
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
        except Exception as err:
            logger.exception(
                "Could not create links for diagram %r, "
                "because an error occured %s",
                obj._short_repr_(),
                err,
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

    def create_grouped_link_fields(
        self,
        data: data_session.ConverterData,
        back_links: (
            dict[str, dict[str, list[polarion_api.WorkItemLink]]] | None
        ) = None,
    ):
        """Create the grouped link fields from the primary work item.

        Parameters
        ----------
        data
            The ConverterData that stores the WorkItem to create the
            fields for.
        back_links
            A dictionary of secondary WorkItem IDs to links to create
            backlinks later.
        """
        work_item = data.work_item
        assert work_item is not None
        wi = f"[{work_item.id}]({work_item.type} {work_item.title})"
        logger.debug("Building grouped links for work item %r...", wi)
        for role, grouped_links in _group_by(
            "role", work_item.linked_work_items
        ).items():
            if (config := find_link_config(data, role)) is not None:
                if back_links is not None and config.reverse_field:
                    for link in grouped_links:
                        back_links.setdefault(
                            link.secondary_work_item_id, {}
                        ).setdefault(config.reverse_field, []).append(link)

                if config.link_field:
                    self._create_link_fields(
                        work_item,
                        config.link_field,
                        grouped_links,
                        config=config,
                    )

    def _create_link_fields(
        self,
        work_item: data_models.CapellaWorkItem,
        role: str,
        links: list[polarion_api.WorkItemLink],
        reverse: bool = False,
        config: converter_config.LinkConfig | None = None,
    ):
        link_map: dict[str, dict[str, list[str]]]
        if reverse:
            link_map = {link.primary_work_item_id: {} for link in links}
        else:
            link_map = {link.secondary_work_item_id: {} for link in links}
            for link_id, include_map in link_map.items():
                if config is None:
                    break

                uuid = self.capella_polarion_mapping.get_capella_uuid(link_id)
                if uuid is None:
                    logger.error(
                        "Did not find work item %r for link field include",
                        link_id,
                    )
                    continue

                try:
                    obj = self.model.by_uuid(uuid)
                except KeyError:
                    logger.error(
                        "Did not find capella element %r for link field "
                        "include",
                        uuid,
                    )
                    continue

                for display_name, attr_name in config.include.items():
                    try:
                        attr = getattr(obj, attr_name)
                    except AttributeError:
                        logger.error(
                            "Couldn't create nested link field."
                            "%r is not a valid attribute on %r.",
                            attr_name,
                            obj._short_repr_(),
                        )

                    if isinstance(attr, common.ElementList):
                        uuids = attr.by_uuid  # type: ignore[assignment]
                    else:
                        assert hasattr(attr, "uuid")
                        uuids = [attr.uuid]

                    work_item_ids = list(
                        self._get_work_item_ids(work_item.id, uuids, attr_name)
                    )
                    include_map[f"{link_id}:{display_name}:{attr_name}"] = (
                        work_item_ids
                    )

        work_item.additional_attributes[role] = {
            "type": "text/html",
            "value": _make_url_list(link_map),
        }

    def create_grouped_back_link_fields(
        self,
        work_item: data_models.CapellaWorkItem,
        links: dict[str, list[polarion_api.WorkItemLink]],
    ):
        """Create fields for the given WorkItem using a list of backlinks.

        Parameters
        ----------
        work_item
            The ConverterData that stores the WorkItem to create the
            fields for.
        links
            Dict of field names and links referencing work_item as secondary.
        """
        wi = f"[{work_item.id}]({work_item.type} {work_item.title})"
        logger.debug("Building grouped back links for work item %r...", wi)
        for reverse_field, grouped_links in links.items():
            self._create_link_fields(
                work_item, reverse_field, grouped_links, True
            )


def find_link_config(
    data: data_session.ConverterData, role: str
) -> converter_config.LinkConfig | None:
    """Search for LinkConfig with matching polarion_role in ``data``."""
    for link_config in data.type_config.links:
        if link_config.polarion_role == role:
            return link_config

    logger.error("No LinkConfig found for %r", role)
    return None


def _group_by(
    attr: str,
    links: cabc.Iterable[polarion_api.WorkItemLink],
) -> dict[str, list[polarion_api.WorkItemLink]]:
    group = defaultdict(list)
    for link in links:
        key = getattr(link, attr)
        group[key].append(link)
    return group


def _make_url_list(link_map: dict[str, dict[str, list[str]]]) -> str:
    urls: list[str] = []
    for link_id in sorted(link_map):
        url = polarion_html_helper.POLARION_WORK_ITEM_URL.format(pid=link_id)
        urls.append(f"<li>{url}</li>")
        for key, include_wids in link_map[link_id].items():
            _, display_name, _ = key.split(":")
            urls.append(
                _sorted_unordered_html_list(include_wids, display_name)
            )

    url_list = "\n".join(urls)
    return f"<ul>{url_list}</ul>"


def _sorted_unordered_html_list(
    work_item_ids: cabc.Iterable[str], heading: str = ""
) -> str:
    urls: list[str] = []
    for pid in work_item_ids:
        url = polarion_html_helper.POLARION_WORK_ITEM_URL.format(pid=pid)
        urls.append(f"<li>{url}</li>")

    urls.sort()
    if heading and urls:
        urls.insert(0, f"<div>{heading}:</div>")

    url_list = "\n".join(urls)
    return f"<ul>{url_list}</ul>"


def _resolve_attribute(
    obj: common.GenericElement, attr_id: str
) -> common.ElementList[common.GenericElement] | common.GenericElement:
    attr_name, _, map_id = attr_id.partition(".")
    objs = getattr(obj, attr_name)
    if map_id:
        if isinstance(objs, common.GenericElement):
            return _resolve_attribute(objs, map_id)
        objs = objs.map(map_id)
    return objs
