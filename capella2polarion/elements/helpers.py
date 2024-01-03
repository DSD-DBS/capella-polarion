# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Helper objects for synchronisation of capella objects to work items."""


def resolve_element_type(type_: str) -> str:
    """Return a valid Type ID for polarion for a given ``obj``."""
    return type_[0].lower() + type_[1:]
