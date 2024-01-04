# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module providing a universal PolarionDataRepository class."""
from __future__ import annotations

import typing

import bidict

from capella2polarion import capella_work_item


class PolarionDataRepository:
    """A mapping class to access all contents by Capella and Polarion IDs.

    This class only holds data already present in the Polarion. It only
    receives updates if data were written to Polarion. There shall be no
    intermediate data stored here during serialization.
    """

    _id_mapping: bidict.bidict[str, str]
    _work_items: dict[str, capella_work_item.CapellaWorkItem]

    def __init__(
        self,
        polarion_work_items: typing.Optional[
            list[capella_work_item.CapellaWorkItem]
        ] = None,
    ):
        if polarion_work_items is None:
            polarion_work_items = []
        self._id_mapping = bidict.bidict(
            {
                work_item.uuid_capella: work_item.id
                for work_item in polarion_work_items
            },
        )
        self._id_mapping.on_dup = bidict.OnDup(
            key=bidict.DROP_OLD, val=bidict.DROP_OLD, kv=bidict.DROP_OLD
        )
        self._work_items = {
            work_item.uuid_capella: work_item
            for work_item in polarion_work_items
        }

    def __contains__(self, item: str) -> bool:
        """Return True, if the given capella UUID is in the repository."""
        return item in self._id_mapping

    def __sizeof__(self):
        """Return the amount of registered Capella UUIDs."""
        return len(self._id_mapping)

    def __getitem__(
        self, item: str
    ) -> typing.Tuple[str, capella_work_item.CapellaWorkItem]:
        """Return the polarion ID and work_item for a given Capella UUID."""
        return self._id_mapping[item], self._work_items[item]

    def __iter__(self) -> typing.Iterator[str]:
        """Iterate all Capella UUIDs."""
        return self._id_mapping.__iter__()

    def items(
        self,
    ):
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
    ) -> capella_work_item.CapellaWorkItem | None:
        """Return a Work Item for a provided Capella UUID."""
        return self._work_items.get(capella_uuid)

    def get_work_item_by_polarion_id(
        self, work_item_id: str
    ) -> capella_work_item.CapellaWorkItem | None:
        """Return a Work Item for a provided Work Item ID."""
        return self.get_work_item_by_capella_uuid(
            self.get_capella_uuid(work_item_id)  # type: ignore
        )

    def update_work_items(
        self,
        work_items: list[capella_work_item.CapellaWorkItem],
    ):
        """Update all mappings for the given Work Items."""
        for work_item in work_items:
            if uuid_capella := self._id_mapping.inverse.get(work_item.id):
                del self._id_mapping[uuid_capella]
                del self._work_items[uuid_capella]

        self._id_mapping.update(
            {
                work_item.uuid_capella: work_item.id
                for work_item in work_items
                if work_item.id is not None
            }
        )
        self._work_items.update(
            {work_item.uuid_capella: work_item for work_item in work_items}
        )

    def remove_work_items_by_capella_uuid(self, uuids: typing.Iterable[str]):
        """Remove entries for the given Capella UUIDs."""
        for uuid in uuids:
            del self._work_items[uuid]
            del self._id_mapping[uuid]
