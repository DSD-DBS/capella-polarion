# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Objects for synchronization of Capella diagrams to polarion."""
from __future__ import annotations

import logging
import typing as t

import polarion_rest_api_client as polarion_api

from capella2polarion.elements import serialize

logger = logging.getLogger(__name__)


def create_diagrams(ctx: dict[str, t.Any]) -> None:
    """Create a set of work items of type ``diagram`` in Polarion."""
    uuids = set(ctx["CAPELLA_UUIDS"]) - set(ctx["POLARION_ID_MAP"])
    diagrams = [diag for diag in ctx["DIAGRAM_IDX"] if diag["uuid"] in uuids]
    work_items = [
        serialize.element(diagram, ctx, serialize.diagram)
        for diagram in diagrams
    ]
    work_items = list(filter(None.__ne__, work_items))
    for work_item in work_items:
        assert work_item is not None
        logger.debug("Create work item for diagram %r...", work_item.title)
    if work_items:
        try:
            ctx["API"].create_work_items(work_items)
        except polarion_api.PolarionApiException as error:
            logger.error("Creating diagrams failed. %s", error.args[0])


def update_diagrams(ctx: dict[str, t.Any]) -> None:
    """Update a set of work items of type ``diagram`` in Polarion."""
    uuids: set[str] = set(ctx["POLARION_ID_MAP"]) & set(ctx["CAPELLA_UUIDS"])
    diagrams = {d["uuid"]: d for d in ctx["DIAGRAM_IDX"] if d["uuid"] in uuids}
    for uuid in uuids:
        wid = ctx["POLARION_ID_MAP"][uuid]
        diagram = diagrams[uuid]
        logger.debug(
            "Update work item %r for diagram %r...", wid, diagram["name"]
        )
        work_item = serialize.element(diagram, ctx, serialize.diagram)
        if work_item is None:
            continue

        work_item.id = wid
        work_item.type = None
        work_item.additional_attributes = None
        work_item.status = "open"

        try:
            ctx["API"].update_work_item(work_item)
        except polarion_api.PolarionApiException as error:
            diag = f"{wid}({diagram['name']})"
            logger.error("Updating diagram %r failed. %s", diag, error.args[0])
