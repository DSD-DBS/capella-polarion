# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Objects for synchronization of Capella diagrams to polarion."""
from __future__ import annotations

import logging
import typing as t

from capella2polarion.elements import serialize

logger = logging.getLogger(__name__)


def create_diagrams(ctx: dict[str, t.Any]) -> list[serialize.CapellaWorkItem]:
    """Return a set of new work items of type ``diagram``."""
    uuids = set(ctx["CAPELLA_UUIDS"]) - set(ctx["POLARION_ID_MAP"])
    diagrams = [diag for diag in ctx["DIAGRAM_IDX"] if diag["uuid"] in uuids]
    work_items = [
        serialize.element(diagram, ctx, serialize.diagram)
        for diagram in diagrams
    ]
    return list(filter(None.__ne__, work_items))  # type:ignore[arg-type]
