# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module providing a universal CapellaPolarionMapping class."""
from __future__ import annotations

import bidict
import capellambse

from capella2polarion.elements import serialize


class CapellaPolarionMapping:
    """A mapping class to access all contents by Capella and Polarion IDs."""

    _description_references: dict[str, set[str]]
    _id_mapping: bidict.bidict[str, str]
    _work_items: dict[str, serialize.CapellaWorkItem]
    _model: capellambse.MelodyModel

    def __init__(
        self,
        model: capellambse.MelodyModel,
        polarion_work_items: list[serialize.CapellaWorkItem],
    ):
        self._description_references = {}
        self._model = model
        self._id_mapping = bidict.bidict(
            {
                work_item.uuid_capella: work_item.id
                for work_item in polarion_work_items
            }
        )
        self._work_items = {
            work_item.uuid_capella: work_item
            for work_item in polarion_work_items
        }

    def get_work_item_id(self, capella_uuid: str) -> str | None:
        """Return a Work Item ID for a given Capella UUID."""
        return self._id_mapping.get(capella_uuid)

    def get_capella_uuid(self, work_item_id: str) -> str | None:
        """Return a Capella UUID for a given Work Item ID."""
        return self._id_mapping.inverse.get(work_item_id)

    def get_work_item_by_capella_uuid(
        self, capella_uuid: str
    ) -> serialize.CapellaWorkItem | None:
        """Return a Work Item for a provided Capella UUID."""
        return self._work_items.get(capella_uuid)

    def get_work_item_by_polarion_id(
        self, work_item_id: str
    ) -> serialize.CapellaWorkItem | None:
        """Return a Work Item for a provided Work Item ID."""
        return self.get_work_item_by_capella_uuid(
            self.get_capella_uuid(work_item_id)  # type: ignore
        )

    def get_model_element_by_capella_uuid(
        self, capella_uuid: str
    ) -> capellambse.model.GenericElement | None:
        """Return a model element for a given Capella UUID."""
        try:
            return self._model.by_uuid(capella_uuid)
        except KeyError:
            return None

    def get_model_element_by_polarion_id(
        self, work_item_id: str
    ) -> capellambse.model.GenericElement | None:
        """Return a model element for a given Work Item ID."""
        return self.get_model_element_by_capella_uuid(
            self.get_capella_uuid(work_item_id)  # type: ignore
        )

    def get_description_references_by_capella_uuid(
        self, capella_uuid: str
    ) -> set[str] | None:
        """Return the description references for a given Capella UUID."""
        return self._description_references.get(capella_uuid)

    def get_description_references_by_polarion_id(
        self, work_item_id: str
    ) -> set[str] | None:
        """Return the description references for a given Work Item ID."""
        return self.get_description_references_by_capella_uuid(
            self.get_capella_uuid(work_item_id)  # type: ignore
        )

    def update_work_items(
        self,
        work_items: serialize.CapellaWorkItem
        | list[serialize.CapellaWorkItem],
    ):
        """Update all mappings for the given Work Items."""
        if isinstance(work_items, serialize.CapellaWorkItem):
            work_items = [work_items]

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

    def update_description_reference(
        self, capella_uuid: str, references: list[str]
    ):
        """Add or replace description references for a given capella UUID."""
        self._description_references.update({capella_uuid: set(references)})
