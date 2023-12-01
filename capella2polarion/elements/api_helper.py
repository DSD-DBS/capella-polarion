# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Capella2Polarion specific helper functions to use the API."""
import collections.abc as cabc
import logging
import typing as t

import polarion_rest_api_client as polarion_api

from capella2polarion.elements import serialize

logger = logging.getLogger(__name__)


def patch_work_item(
    api: polarion_api.OpenAPIPolarionProjectClient,
    new: serialize.CapellaWorkItem,
    old: serialize.CapellaWorkItem,
    name: str,
    _type: str,
):
    """Patch a given WorkItem.

    Parameters
    ----------
    api
        The context to execute the patch for.
    new
        The updated CapellaWorkItem
    old
        The CapellaWorkItem currently present on polarion
    name
        The name of the object, which should be displayed in log
        messages.
    _type
        The type of element, which should be shown in log messages.
    """
    if new == old:
        return

    log_args = (old.id, _type, name)
    logger.info("Update work item %r for model %s %r...", *log_args)
    if "uuid_capella" in new.additional_attributes:
        del new.additional_attributes["uuid_capella"]

    old.linked_work_items = api.get_all_work_item_links(old.id)
    new.type = None
    new.status = "open"
    new.id = old.id
    try:
        api.update_work_item(new)
        handle_links(
            old.linked_work_items,
            new.linked_work_items,
            ("Delete", _type, name),
            api.delete_work_item_links,
        )
        handle_links(
            new.linked_work_items,
            old.linked_work_items,
            ("Create", _type, name),
            api.create_work_item_links,
        )
    except polarion_api.PolarionApiException as error:
        wi = f"{old.id}({_type} {name})"
        logger.error("Updating work item %r failed. %s", wi, error.args[0])


def handle_links(
    left: cabc.Iterable[polarion_api.WorkItemLink],
    right: cabc.Iterable[polarion_api.WorkItemLink],
    log_args: tuple[str, ...],
    handler: cabc.Callable[[cabc.Iterable[polarion_api.WorkItemLink]], t.Any],
):
    """Handle work item links on Polarion."""
    for link in (links := get_links(left, right)):
        largs = (log_args[0], _get_link_id(link), *log_args[1:])
        logger.info("%s work item link %r for model %s %r", *largs)
    if links:
        handler(links)


def get_links(
    left: cabc.Iterable[polarion_api.WorkItemLink],
    right: cabc.Iterable[polarion_api.WorkItemLink],
) -> list[polarion_api.WorkItemLink]:
    """Return new work item links for ceate and dead links for delete."""
    news = {_get_link_id(link): link for link in left}
    olds = {_get_link_id(link): link for link in right}
    return [news[lid] for lid in set(news) - set(olds)]


def _get_link_id(link: polarion_api.WorkItemLink) -> str:
    return "/".join(
        (
            link.primary_work_item_id,
            link.role,
            link.secondary_work_item_project,
            link.secondary_work_item_id,
        )
    )
