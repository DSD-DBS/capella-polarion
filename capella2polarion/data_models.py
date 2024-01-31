# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module providing the CapellaWorkItem class."""
from __future__ import annotations

import typing as t

import polarion_rest_api_client as polarion_api


class CapellaWorkItem(polarion_api.WorkItem):
    """A custom WorkItem class with additional capella related attributes."""

    class Condition(t.TypedDict):
        """A class to describe a pre or post condition."""

        type: str
        value: str

    uuid_capella: str
    preCondition: Condition | None
    postCondition: Condition | None

    def __add__(self, other: CapellaWorkItem) -> CapellaWorkItem:
        """Add a CapellaWorkItem to this one."""
        if not isinstance(other, CapellaWorkItem):
            raise TypeError("Can only merge WorkItems")

        merged_data: dict[str, t.Any] = {}
        self_dict = self.to_dict()
        other_dict = other.to_dict()
        for key in set(self_dict) | set(other_dict):
            self_val: t.Any = self_dict.get(key)
            other_val: t.Any = other_dict.get(key)

            if isinstance(self_val, list) and isinstance(other_val, list):
                merged_data[key] = self_val + other_val
            elif isinstance(self_val, dict) and isinstance(other_val, dict):
                merged_data[key] = {**self_val, **other_val}
            else:
                merged_data[key] = (
                    other_val if other_val is not None else self_val
                )
        return CapellaWorkItem(**merged_data)
