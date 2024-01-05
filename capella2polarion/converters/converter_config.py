# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module providing capella2polarion config class."""
from __future__ import annotations

import dataclasses
import typing

import yaml


@dataclasses.dataclass
class CapellaTypeConfig:
    """A single Capella Type configuration."""

    p_type: str | None = None
    converter: str | None = None
    links: list[str] = dataclasses.field(default_factory=list)


class ConverterConfig:
    """The overall Config for capella2polarion."""

    def __init__(self, synchronize_config: typing.TextIO):
        config_dict = yaml.safe_load(synchronize_config)
        self._layer_configs: dict[str, dict[str, CapellaTypeConfig]] = {}
        self._global_configs: dict[str, CapellaTypeConfig] = {}
        # We handle the cross layer config separately as global_configs
        global_config_dict = config_dict.pop("*", {})
        all_type_config = global_config_dict.pop("*", {})
        global_links = all_type_config.get("links", [])
        self.__global_config = CapellaTypeConfig(links=global_links)

        for c_type, type_config in global_config_dict.items():
            type_config = type_config or {}
            self._global_configs[c_type] = CapellaTypeConfig(
                type_config.get("polarion_type"),
                type_config.get("serializer"),
                type_config.get("links", []) + global_links,
            )

        for layer, type_configs in config_dict.items():
            self._layer_configs[layer] = {}
            for c_type, type_config in type_configs.items():
                self._layer_configs[layer][c_type] = CapellaTypeConfig(
                    type_config.get("polarion_type")
                    or self._global_configs.get(
                        c_type, self.__global_config
                    ).p_type,
                    type_config.get("serializer")
                    or self._global_configs.get(
                        c_type, self.__global_config
                    ).converter,
                    type_config.get("links", [])
                    + self._global_configs.get(
                        c_type, self.__global_config
                    ).links,
                )

    def _default_type_conversion(self, c_type: str) -> str:
        return c_type[0].lower() + c_type[1:]

    def _get_type_configs(
        self, layer: str, c_type: str
    ) -> CapellaTypeConfig | None:
        return self._layer_configs.get(layer, {}).get(
            c_type
        ) or self._global_configs.get(c_type)

    def get_polarion_type(self, layer: str, c_type: str) -> str:
        """Return polarion type for a given layer and Capella type."""
        type_config = (
            self._get_type_configs(layer, c_type) or self.__global_config
        )
        return type_config.p_type or self._default_type_conversion(c_type)

    def get_serializer(self, layer: str, c_type: str) -> str | None:
        """Return the serializer name for a given layer and Capella type."""
        type_config = (
            self._get_type_configs(layer, c_type) or self.__global_config
        )
        return type_config.converter

    def get_links(self, layer: str, c_type: str) -> list[str]:
        """Return the list of link types for a given layer and Capella type."""
        type_config = (
            self._get_type_configs(layer, c_type) or self.__global_config
        )
        return type_config.links

    def __contains__(self, item: tuple[str, str]):
        """Check if there is a config for a given layer and Capella type."""
        layer, c_type = item
        return self._get_type_configs(layer, c_type) is not None
