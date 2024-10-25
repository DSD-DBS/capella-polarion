# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module providing a universal PolarionDataRepository class."""
from __future__ import annotations

import collections.abc as cabc

import bidict
import polarion_rest_api_client as polarion_api

from capella2polarion import data_model


class PolarionDataRepository:
    """A mapping to access all contents by Capella and Polarion IDs.

    This class only holds data already present in Polarion. It only
    receives updates if data were written to Polarion. There shall be no
    intermediate data stored here during serialization.
    """

    _id_mapping: bidict.bidict[str, str]
    _work_items: dict[str, data_model.CapellaWorkItem]

    def __init__(
        self,
        polarion_work_items: list[data_model.CapellaWorkItem] | None = None,
    ):
        if polarion_work_items is None:
            polarion_work_items = []

        check_work_items(polarion_work_items)
        self._id_mapping = bidict.bidict(
            {
                work_item.uuid_capella: work_item.id
                for work_item in polarion_work_items
            },  # type: ignore[arg-type]
        )
        self._id_mapping.on_dup = bidict.OnDup(
            key=bidict.DROP_OLD, val=bidict.DROP_OLD
        )
        self._work_items = {
            work_item.uuid_capella: work_item
            for work_item in polarion_work_items
        }

    def __contains__(self, item: str) -> bool:
        """Return True, if the given capella UUID is in the repository."""
        return item in self._id_mapping

    def __len__(self) -> int:
        """Return the amount of registered Capella UUIDs."""
        return len(self._id_mapping)

    def __iter__(self) -> cabc.Iterator[str]:
        """Iterate all Capella UUIDs."""
        return self._id_mapping.__iter__()

    def items(
        self,
    ) -> cabc.Iterator[tuple[str, str, data_model.CapellaWorkItem]]:
        """Yield all Capella UUIDs, Work Item IDs and Work Items."""
        for uuid, polarion_id in self._id_mapping.items():
            yield uuid, polarion_id, self._work_items[uuid]

    def get_work_item_id(self, capella_uuid: str) -> str | None:
        """Return a Work Item ID for a given Capella UUID."""
        return self._id_mapping.get(capella_uuid)

    def get_capella_uuid(self, work_item_id: str) -> str | None:
        """Return a Capella UUID for a given Work Item ID."""
        return self._id_mapping.inverse.get(work_item_id)

    def get_work_item_by_capella_uuid(
        self, capella_uuid: str
    ) -> data_model.CapellaWorkItem | None:
        """Return a Work Item for a provided Capella UUID."""
        return self._work_items.get(capella_uuid)

    def get_work_item_by_polarion_id(
        self, work_item_id: str
    ) -> data_model.CapellaWorkItem | None:
        """Return a Work Item for a provided Work Item ID."""
        return self.get_work_item_by_capella_uuid(
            self.get_capella_uuid(work_item_id)  # type: ignore
        )

    def update_work_items(self, work_items: list[data_model.CapellaWorkItem]):
        """Update all mappings for the given Work Items."""
        for work_item in work_items:
            assert work_item.id is not None
            if uuid_capella := self._id_mapping.inverse.get(work_item.id):
                del self._id_mapping[uuid_capella]
                del self._work_items[uuid_capella]

        check_work_items(work_items)
        self._id_mapping.update(
            {
                work_item.uuid_capella: work_item.id
                for work_item in work_items
            }  # type: ignore[arg-type]
        )
        self._work_items.update(
            {work_item.uuid_capella: work_item for work_item in work_items}
        )

    def remove_work_items_by_capella_uuid(self, uuids: cabc.Iterable[str]):
        """Remove entries for the given Capella UUIDs."""
        for uuid in uuids:
            del self._work_items[uuid]
            del self._id_mapping[uuid]


DocumentRepository = dict[
    tuple[str | None, str, str],
    tuple[polarion_api.Document | None, list[polarion_api.WorkItem]],
]
"""A dict providing a mapping for documents and their text workitems.

It has (project, space, name) of the document as key and (document,
workitems) as value. The project can be None and the None value means
that the document is in the same project as the model sync work items.
"""


def check_work_items(work_items: cabc.Iterable[data_model.CapellaWorkItem]):
    """Raise a ``ValueError`` if any work item has no ID."""
    if work_item_without_id := next(
        (wi for wi in work_items if wi.id is None), None
    ):
        raise ValueError(
            f"Found Work Item without ID: {work_item_without_id.title!r}"
        )
