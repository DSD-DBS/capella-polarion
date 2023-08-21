# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Capella2Polarion specific helper functions to use the API."""
import collections.abc as cabc
import logging
import typing as t

import polarion_rest_api_client as polarion_api
from capellambse.model import common

from capella2polarion.elements import serialize

logger = logging.getLogger(__name__)


class Diagram(t.TypedDict):
    """A Diagram object from the Diagram Cache Index."""

    uuid: str
    name: str
    success: bool


def patch_work_item(
    ctx: dict[str, t.Any],
    wid: str,
    obj: common.GenericElement | Diagram,
    serializer: cabc.Callable[
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
    wid
        The ID of the polarion WorkItem
    obj
        The Capella object to update the WorkItem from
    serializer
        The serializer, which should be used to create the WorkItem.
    name
        The name of the object, which should be displayed in log messages.
    _type
        The type of element, which should be shown in log messages.
    """
    logger.debug(
        "Update work item %r for model %s %r...",
        wid,
        _type,
        name,
    )
    if new := serialize.element(obj, ctx, serializer):
        uuid = obj["uuid"] if isinstance(obj, dict) else obj.uuid
        old: serialize.CapellaWorkItem = ctx["POLARION_WI_MAP"][uuid]
        if new.checksum == old.checksum:
            return

        if new.uuid_capella:
            del new.additional_attributes["uuid_capella"]

        new.type = None
        new.status = "open"
        new.id = wid
        try:
            ctx["API"].update_work_item(new)
        except polarion_api.PolarionApiException as error:
            wi = f"{wid}({_type} {name})"
            logger.error("Updating work item %r failed. %s", wi, error.args[0])
