# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""A module to store data during the conversion process."""
from __future__ import annotations

import dataclasses

from capellambse.model import common, diagram

from capella2polarion import data_models as dm
from capella2polarion.converters import converter_config


@dataclasses.dataclass
class ConverterData:
    """Data class holding all information needed during Conversion."""

    layer: str
    type_config: converter_config.CapellaTypeConfig
    capella_element: diagram.Diagram | common.GenericElement
    work_item: dm.CapellaWorkItem | None = None
    description_references: list[str] = dataclasses.field(default_factory=list)
    errors: set[str] = dataclasses.field(default_factory=set)


ConverterSession = dict[str, ConverterData]
