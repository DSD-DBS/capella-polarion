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
    ctx
        The context to execute the patch for.
    wid
        The ID of the polarion WorkItem
    capella_object
        The capella object to update the WorkItem from
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
    if work_item := serialize.element(capella_object, ctx, serializer):
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
