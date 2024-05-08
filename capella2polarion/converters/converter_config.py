# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module providing capella2polarion config class."""
from __future__ import annotations

import dataclasses
import logging
import typing as t
from collections import abc as cabc

import yaml

logger = logging.getLogger(__name__)

_C2P_DEFAULT = "_C2P_DEFAULT"


@dataclasses.dataclass
class LinkConfig:
    """A single Capella Link configuration.

    Attributes
    ----------
    capella_attr
        The Attribute name on the capellambse model object.
    polarion_role
        The identifier used in the Polarion configuration for this work
        item link (role).
    include
        A list of identifiers that are attribute names on the Capella
        objects link targets. The requested objects are then included in
        the list display in the grouped link custom field as nested
        lists. They also need be migrated for working references.
    """

    capella_attr: str | None = None
    polarion_role: str | None = None
    include: dict[str, str] = dataclasses.field(default_factory=dict)


@dataclasses.dataclass
class CapellaTypeConfig:
    """A single Capella Type configuration."""

    p_type: str | None = None
    converters: str | list[str] | dict[str, dict[str, t.Any]] | None = None
    links: list[LinkConfig] = dataclasses.field(default_factory=list)
    is_actor: bool | None = None
    nature: str | None = None

    def __post_init__(self):
        """Post processing for the initialization."""
        self.converters = _force_dict(self.converters)


def _default_type_conversion(c_type: str) -> str:
    return c_type[0].lower() + c_type[1:]


class ConverterConfig:
    """The overall Config for capella2polarion."""

    def __init__(self):
        self._layer_configs: dict[str, dict[str, list[CapellaTypeConfig]]] = {}
        self._global_configs: dict[str, CapellaTypeConfig] = {}
        self.polarion_types = set[str]()
        self.diagram_config: CapellaTypeConfig | None = None
        self.__global_config = CapellaTypeConfig()

    def read_config_file(self, synchronize_config: t.TextIO):
        """Read a given yaml file as config."""
        config_dict = yaml.safe_load(synchronize_config)
        # We handle the cross layer config separately as global_configs
        global_config_dict = config_dict.pop("*", {})
        all_type_config = global_config_dict.pop("*", {})
        global_links = all_type_config.get("links", [])
        self.__global_config.links = _force_link_config(global_links)

        if "Diagram" in global_config_dict:
            diagram_config = global_config_dict.pop("Diagram") or {}
            self.set_diagram_config(diagram_config)

        for c_type, type_config in global_config_dict.items():
            type_config = type_config or {}
            self.set_global_config(c_type, type_config)

        for layer, type_configs in config_dict.items():
            type_configs = type_configs or {}
            self.add_layer(layer)
            for c_type, c_type_config in type_configs.items():
                self.set_layer_config(c_type, c_type_config, layer)

    def add_layer(self, layer: str):
        """Add a new layer without configuring any types."""
        self._layer_configs[layer] = {}

    def set_layer_config(
        self,
        c_type: str,
        c_type_config: dict[str, t.Any] | list[dict[str, t.Any]] | None,
        layer: str,
    ):
        """Set one or multiple configs for a type to an existing layer."""
        type_configs = _read_capella_type_configs(c_type_config)
        self._layer_configs[layer][c_type] = []
        for type_config in type_configs:
            closest_config = (
                self.get_type_config(
                    layer,
                    c_type,
                    actor=type_config.get("is_actor", _C2P_DEFAULT),
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
                    type_config.get("serializer") or closest_config.converters,
                    _force_link_config(type_config.get("links", []))
                    + closest_config.links,
                    type_config.get("is_actor", _C2P_DEFAULT),
                    type_config.get("nature", _C2P_DEFAULT),
                )
            )

    def set_global_config(self, c_type: str, type_config: dict[str, t.Any]):
        """Set a global config for a specific type."""
        p_type = type_config.get("polarion_type") or _default_type_conversion(
            c_type
        )
        self.polarion_types.add(p_type)
        self._global_configs[c_type] = CapellaTypeConfig(
            p_type,
            type_config.get("serializer"),
            _force_link_config(type_config.get("links", []))
            + self.__global_config.links,
            type_config.get("is_actor", _C2P_DEFAULT),
            type_config.get("nature", _C2P_DEFAULT),
        )

    def set_diagram_config(self, diagram_config: dict[str, t.Any]):
        """Set the diagram config."""
        p_type = diagram_config.get("polarion_type") or "diagram"
        self.polarion_types.add(p_type)
        links = _force_link_config(diagram_config.get("links", []))
        self.diagram_config = CapellaTypeConfig(
            p_type,
            diagram_config.get("serializer") or "diagram",
            links + self.__global_config.links,
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


def _read_capella_type_configs(
    conf: dict[str, t.Any] | list[dict[str, t.Any]] | None
) -> list[dict]:
    if conf is None:
        return [{}]
    if isinstance(conf, dict):
        return [conf]

    # We want to have the most generic config first followed by those
    # having is_actor set to None
    return sorted(
        conf,
        key=lambda c: int(c.get("is_actor", _C2P_DEFAULT) != _C2P_DEFAULT)
        + 2 * int(c.get("nature", _C2P_DEFAULT) != _C2P_DEFAULT),
    )


def _force_dict(
    config: str | list[str] | dict[str, dict[str, t.Any]] | None
) -> dict[str, dict[str, t.Any]]:
    match config:
        case None:
            return {}
        case str():
            return {config: {}}
        case list():
            return {c: {} for c in config}
        case dict():
            return {k: v or {} for k, v in config.items()}
        case _:
            raise TypeError("Unsupported Type")


def _force_link_config(links: t.Any) -> list[LinkConfig]:
    result: list[LinkConfig] = []
    for link in links:
        if isinstance(link, str):
            config = LinkConfig(capella_attr=link, polarion_role=link)
        elif isinstance(link, dict):
            config = LinkConfig(
                capella_attr=(lid := link.get("capella_attr")),
                polarion_role=link.get("polarion_role", lid),
                include=link.get("include", {}),
            )
        else:
            logger.error(
                "Link not configured correctly: %r",
                link,
            )
            continue
        result.append(config)
    return result
