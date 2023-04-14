# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Objects for synchronization of Capella diagrams to polarion."""

import logging
import typing as t

from capella2polarion import polarion_api
from capella2polarion.elements import serialize

logger = logging.getLogger(__name__)


def create_diagrams(ctx: dict[str, t.Any]) -> None:
    """Create a set of work items of type ``diagram`` in Polarion."""

    def serialize_for_create(
        diagram: dict[str, t.Any]
    ) -> polarion_api.WorkItem | None:
        attributes = serialize.element(diagram, ctx, serialize.diagram)
        if attributes is None:
            return None
        return polarion_api.WorkItem(**attributes)

    uuids = set(ctx["CAPELLA_UUIDS"]) - set(ctx["POLARION_ID_MAP"])
    diagrams = [diag for diag in ctx["DIAGRAM_IDX"] if diag["uuid"] in uuids]
    work_items = [serialize_for_create(diagram) for diagram in diagrams]
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
        attributes = serialize.element(diagram, ctx, serialize.diagram)
        if attributes is None:
            continue

        del attributes["type"]
        del attributes["uuid_capella"]
        attributes["status"] = "open"
        try:
            ctx["API"].update_work_item(
                polarion_api.WorkItem(wid, **attributes)
            )
        except polarion_api.PolarionApiException as error:
            diag = f"{wid}({diagram['name']})"
            logger.error("Updating diagram %r failed. %s", diag, error.args[0])
