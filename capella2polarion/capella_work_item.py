# Copyright DB Netz AG and contributors
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
