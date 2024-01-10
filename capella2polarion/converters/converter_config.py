# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module providing capella2polarion config class."""
from __future__ import annotations

import dataclasses
import typing as t
from collections import abc as cabc

import yaml

_C2P_DEFAULT = "_C2P_DEFAULT"


@dataclasses.dataclass
class CapellaTypeConfig:
    """A single Capella Type configuration."""

    p_type: str | None = None
    converter: str | None = None
    links: list[str] = dataclasses.field(default_factory=list)
    actor: bool | None = None
    nature: bool | None = None


def _default_type_conversion(c_type: str) -> str:
    return c_type[0].lower() + c_type[1:]


class ConverterConfig:
    """The overall Config for capella2polarion."""

    def __init__(self, synchronize_config: t.TextIO):
        config_dict = yaml.safe_load(synchronize_config)
        self._layer_configs: dict[str, dict[str, list[CapellaTypeConfig]]] = {}
        self._global_configs: dict[str, CapellaTypeConfig] = {}
        self.polarion_types = set[str]()
        self.diagram_config: CapellaTypeConfig | None = None

        # We handle the cross layer config separately as global_configs
        global_config_dict = config_dict.pop("*", {})
        all_type_config = global_config_dict.pop("*", {})
        global_links = all_type_config.get("links", [])
        self.__global_config = CapellaTypeConfig(links=global_links)

        if "Diagram" in global_config_dict:
            diagram_config = global_config_dict.pop("Diagram") or {}
            p_type = diagram_config.get("polarion_type") or "diagram"
            self.polarion_types.add(p_type)
            self.diagram_config = CapellaTypeConfig(
                p_type,
                diagram_config.get("serializer"),
                diagram_config.get("links", []) + global_links,
            )

        def _read_capella_type_configs(conf: dict | list | None) -> list[dict]:
            if conf is None:
                return [{}]
            if isinstance(conf, dict):
                return [conf]

            # We want to have the most generic config first followed by those
            # having actor set to None
            return sorted(
                conf,
                key=lambda c: int(c.get("actor", _C2P_DEFAULT) != _C2P_DEFAULT)
                + 2 * int(c.get("nature", _C2P_DEFAULT) != _C2P_DEFAULT),
            )

        for c_type, type_config in global_config_dict.items():
            type_config = type_config or {}
            p_type = type_config.get(
                "polarion_type"
            ) or _default_type_conversion(c_type)
            self.polarion_types.add(p_type)
            self._global_configs[c_type] = CapellaTypeConfig(
                p_type,
                type_config.get("serializer"),
                type_config.get("links", []) + global_links,
                type_config.get("actor", _C2P_DEFAULT),
                type_config.get("nature", _C2P_DEFAULT),
            )

        for layer, type_configs in config_dict.items():
            type_configs = type_configs or {}
            self._layer_configs[layer] = {}
            for c_type, c_type_config in type_configs.items():
                type_configs = _read_capella_type_configs(c_type_config)
                self._layer_configs[layer][c_type] = []
                for type_config in type_configs:
                    closest_config = (
                        self.get_type_config(
                            layer,
                            c_type,
                            actor=type_config.get("actor", _C2P_DEFAULT),
                            nature=type_config.get("nature", _C2P_DEFAULT),
                        )
                        or self.__global_config
                    )
                    p_type = (
                        type_config.get("polarion_type")
                        or closest_config.p_type
                        or _default_type_conversion(c_type)
                    )
                    self.polarion_types.add(p_type)
                    self._layer_configs[layer][c_type].append(
                        CapellaTypeConfig(
                            p_type,
                            type_config.get("serializer")
                            or closest_config.converter,
                            type_config.get("links", [])
                            + closest_config.links,
                            type_config.get("actor", _C2P_DEFAULT),
                            type_config.get("nature", _C2P_DEFAULT),
                        )
                    )

    def get_type_config(
        self, layer: str, c_type: str, **attributes: t.Any
    ) -> CapellaTypeConfig | None:
        """Get the type config for a given layer and capella_type."""
        if layer not in self._layer_configs:
            return None

        layer_configs = self._layer_configs.get(layer, {}).get(c_type, [])
        for config in layer_configs[::-1]:
            if config_matches(config, **attributes):
                return config
        return self._global_configs.get(c_type)

    def __contains__(
        self,
        item: tuple[str, str, dict[str, t.Any]],
    ):
        """Check if there is a config for a given layer and Capella type."""
        layer, c_type, attributes = item
        return self.get_type_config(layer, c_type, **attributes) is not None

    def layers_and_types(self) -> cabc.Iterator[tuple[str, str]]:
        """Yield the layer and Capella type of the config."""
        for layer, layer_types in self._layer_configs.items():
            for c_type in layer_types:
                yield layer, c_type
            for c_type in self._global_configs:
                if c_type not in layer_types:
                    yield layer, c_type


def config_matches(config: CapellaTypeConfig | None, **kwargs: t.Any) -> bool:
    """Check whether the given ``config`` matches the given ``kwargs``."""
    if config is None:
        return False

    default_attr = _C2P_DEFAULT
    for attr_name, attr in kwargs.items():
        if getattr(config, attr_name, default_attr) not in {
            attr,
            default_attr,
        }:
            return False
    return True
