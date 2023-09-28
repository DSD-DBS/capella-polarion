# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Capella2Polarion specific helper functions to use the API."""
import base64
import collections.abc as cabc
import io
import logging
import re
import typing as t

import polarion_rest_api_client as polarion_api
from capellambse.model import common
from PIL import Image, ImageChops

from capella2polarion.elements import serialize

logger = logging.getLogger(__name__)


def patch_work_item(
    ctx: dict[str, t.Any],
    obj: common.GenericElement,
    receiver: cabc.Callable[
        [t.Any, dict[str, t.Any]], serialize.CapellaWorkItem
    ],
    name: str,
    _type: str,
):
    """Patch a given WorkItem.

    Parameters
    ----------
    ctx
        The context to execute the patch for.
    obj
        The Capella object to update the WorkItem from
    receiver
        A function that receives the WorkItem from the created
        instances.
    name
        The name of the object, which should be displayed in log messages.
    _type
        The type of element, which should be shown in log messages.
    """
    if new := receiver(obj, ctx):
        wid = ctx["POLARION_ID_MAP"][obj.uuid]
        old: serialize.CapellaWorkItem = ctx["POLARION_WI_MAP"][obj.uuid]

        if _type == "diagram" and has_visual_changes(
            old.description, new.description
        ):
            return

        if new == old:
            return

        log_args = (wid, _type, name)
        logger.info("Update work item %r for model %s %r...", *log_args)
        if new.uuid_capella:
            del new.additional_attributes["uuid_capella"]

        old.linked_work_items = ctx["API"].get_all_work_item_links(old.id)
        new.type = None
        new.status = "open"
        new.id = wid
        try:
            ctx["API"].update_work_item(new)
            handle_links(
                old.linked_work_items,
                new.linked_work_items,
                ("Delete", _type, name),
                ctx["API"].delete_work_item_links,
            )
            handle_links(
                new.linked_work_items,
                old.linked_work_items,
                ("Create", _type, name),
                ctx["API"].create_work_item_links,
            )
        except polarion_api.PolarionApiException as error:
            wi = f"{wid}({_type} {name})"
            logger.error("Updating work item %r failed. %s", wi, error.args[0])


def decode_diagram(dia: str):
    """Decode a diagram from a base64 string."""
    encoded = dia.replace("data:image/", "").split(";base64,", 1)

    decoded = base64.b64decode(encoded[1])

    return encoded[0], decoded


def has_visual_changes(old: str, new: str) -> bool:
    """Return True if the images of the diagrams differ."""
    type_old, decoded_old = decode_diagram(old)
    type_new, decoded_new = decode_diagram(new)

    if type_old != type_new:
        return True

    if type_old == "svg+xml":
        d_new = decoded_new.decode("utf-8").splitlines()
        for i, d_old in enumerate(decoded_old.decode("utf-8").splitlines()):
            if re.sub(r'id=["\'][^"\']*["\']', "", d_old) != re.sub(
                r'id=["\'][^"\']*["\']', "", d_new[i]
            ):
                return True
        return False

    image_old = Image.open(io.BytesIO(decoded_old))
    image_new = Image.open(io.BytesIO(decoded_new))

    diff = ImageChops.difference(image_old, image_new)

    return bool(diff.getbbox())


def handle_links(
    left: cabc.Iterable[polarion_api.WorkItemLink],
    right: cabc.Iterable[polarion_api.WorkItemLink],
    log_args: tuple[str, ...],
    handler: cabc.Callable[[cabc.Iterable[polarion_api.WorkItemLink]], None],
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
