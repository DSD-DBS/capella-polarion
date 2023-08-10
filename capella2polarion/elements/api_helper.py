# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Capella2Polarion specific helper functions to use the API."""
import collections.abc as cabc
import logging
import typing as t

import polarion_rest_api_client as polarion_api
from capellambse.model.common import element

from capella2polarion.elements import serialize

logger = logging.getLogger(__name__)


def patch_work_item(
    ctx: dict[str, t.Any],
    wid: str,
    capella_object: element.GenericElement,
    serializer: cabc.Callable[
        [t.Any, dict[str, t.Any]], serialize.CapellaWorkItem
    ],
    name: str,
    _type: str,
):
    """Patch a given WorkItem.

    Parameters
    ----------
    ctx : dict[str, t.Any]
        The context to execute the patch for.
    wid : str
        The ID of the polarion WorkItem
    capella_object : element.GenericElement
        The capella object to update the WorkItem from
    serializer : cabc.Callable
        The serializer, which should be used to create the WorkItem.
    name : str
        The name of the object, which should be displayed in log messages.
    _type : str
        The type of element, which should be shown in log messages.
    """
    logger.debug(
        "Update work item %r for model %r %r...",
        wid,
        _type,
        name,
    )
    work_item = serialize.element(capella_object, ctx, serializer)

    if work_item is not None:
        if work_item.uuid_capella:
            del work_item.additional_attributes["uuid_capella"]

        work_item.type = None
        work_item.status = "open"
        work_item.id = wid

        try:
            ctx["API"].update_work_item(work_item)
        except polarion_api.PolarionApiException as error:
            wi = f"{wid}({_type} {name})"
            logger.error("Updating work item %r failed. %s", wi, error.args[0])
