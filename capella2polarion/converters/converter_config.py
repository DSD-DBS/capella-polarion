# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module providing capella2polarion config class."""
from __future__ import annotations

import dataclasses
import logging
import typing as t
from collections import abc as cabc

import yaml
from capellambse import model as m
from capellambse_context_diagrams import filters as context_filters

logger = logging.getLogger(__name__)

_C2P_DEFAULT = "_C2P_DEFAULT"
DESCRIPTION_REFERENCE_SERIALIZER = "description_reference"
DIAGRAM_ELEMENTS_SERIALIZER = "diagram_elements"


@dataclasses.dataclass
class LinkConfig:
    """A single Capella Link configuration."""

    capella_attr: str
    """The Attribute name on the capellambse model object."""
    polarion_role: str
    """The identifier used in the Polarion configuration for this work item
    link (role)."""
    include: dict[str, str] = dataclasses.field(default_factory=dict)
    """A list of identifiers that are attribute names on the Capella objects
    link targets.

    The requested objects are then included in the list display in the
    grouped link custom field as nested lists. They also need be
    migrated for working references.
    """
    link_field: str = ""
    reverse_field: str = ""


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
        self.polarion_types: set[str] = set()
        self.diagram_config: CapellaTypeConfig | None = None
        self.__global_config = CapellaTypeConfig()

    def read_config_file(
        self,
        synchronize_config: t.TextIO,
        type_prefix: str = "",
        role_prefix: str = "",
    ):
        """Read a given yaml file as config."""
        config_dict = yaml.safe_load(synchronize_config)
        # We handle the cross layer config separately as global_configs
        global_config_dict = config_dict.pop("*", {})
        all_type_config = global_config_dict.pop("*", {})
        global_links = all_type_config.get("links", [])
        self.__global_config.links = self._force_link_config(
            global_links, role_prefix
        )

        if "Diagram" in global_config_dict:
            diagram_config = global_config_dict.pop("Diagram") or {}
            self.set_diagram_config(diagram_config, type_prefix, role_prefix)

        for c_type, type_config in global_config_dict.items():
            type_config = type_config or {}
            self.set_global_config(
                c_type, type_config, type_prefix, role_prefix
            )

        for layer, type_configs in config_dict.items():
            type_configs = type_configs or {}
            self.add_layer(layer)
            for c_type, c_type_config in type_configs.items():
                self.set_layer_config(
                    c_type, c_type_config, layer, type_prefix, role_prefix
                )

    def add_layer(self, layer: str):
        """Add a new layer without configuring any types."""
        self._layer_configs[layer] = {}

    def _get_global_links(self, c_type: str) -> list[LinkConfig]:
        return _filter_links(c_type, self.__global_config.links, True)

    def set_layer_config(
        self,
        c_type: str,
        c_type_config: dict[str, t.Any] | list[dict[str, t.Any]] | None,
        layer: str,
        type_prefix: str = "",
        role_prefix: str = "",
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
            # As we set up all types this way, we can expect that all
            # non-compliant links are coming from global context here
            closest_links = _filter_links(c_type, closest_config.links, True)
            p_type = add_prefix(
                (
                    type_config.get("polarion_type")
                    or closest_config.p_type
                    or _default_type_conversion(c_type)
                ),
                type_prefix,
            )
            self.polarion_types.add(p_type)
            links = self._force_link_config(
                type_config.get("links", []), role_prefix
            )
            self._layer_configs[layer][c_type].append(
                CapellaTypeConfig(
                    p_type,
                    type_config.get("serializer") or closest_config.converters,
                    _filter_links(c_type, links) + closest_links,
                    type_config.get("is_actor", _C2P_DEFAULT),
                    type_config.get("nature", _C2P_DEFAULT),
                )
            )

    def set_global_config(
        self,
        c_type: str,
        type_config: dict[str, t.Any],
        type_prefix: str = "",
        role_prefix: str = "",
    ):
        """Set a global config for a specific type."""
        p_type = add_prefix(
            type_config.get("polarion_type")
            or _default_type_conversion(c_type),
            type_prefix,
        )
        self.polarion_types.add(p_type)
        link_config = self._force_link_config(
            type_config.get("links", []), role_prefix
        )
        self._global_configs[c_type] = CapellaTypeConfig(
            p_type,
            type_config.get("serializer"),
            _filter_links(c_type, link_config)
            + self._get_global_links(c_type),
            type_config.get("is_actor", _C2P_DEFAULT),
            type_config.get("nature", _C2P_DEFAULT),
        )

    def set_diagram_config(
        self,
        diagram_config: dict[str, t.Any],
        type_prefix: str = "",
        role_prefix: str = "",
    ):
        """Set the diagram config."""
        c_type = "diagram"
        p_type = add_prefix(
            diagram_config.get("polarion_type") or "diagram", type_prefix
        )
        self.polarion_types.add(p_type)
        link_config = self._force_link_config(
            diagram_config.get("links", []), role_prefix
        )
        links = _filter_links(c_type, link_config)
        self.diagram_config = CapellaTypeConfig(
            p_type,
            diagram_config.get("serializer") or "diagram",
            links + self._get_global_links(c_type),
        )

    def _force_link_config(
        self, links: t.Any, role_prefix: str = ""
    ) -> list[LinkConfig]:
        result: list[LinkConfig] = []
        for link in links:
            if isinstance(link, str):
                config = LinkConfig(
                    capella_attr=link,
                    polarion_role=add_prefix(link, role_prefix),
                    link_field=link,
                    reverse_field=f"{link}_reverse",
                )
            elif isinstance(link, dict):
                config = LinkConfig(
                    capella_attr=(lid := link["capella_attr"]),
                    polarion_role=add_prefix(
                        (pid := link.get("polarion_role", lid)),
                        role_prefix,
                    ),
                    include=link.get("include", {}),
                    link_field=(lf := link.get("link_field", pid)),
                    reverse_field=link.get("reverse_field", f"{lf}_reverse"),
                )
            else:
                logger.error(
                    "Link not configured correctly: %r",
                    link,
                )
                continue
            result.append(config)
        return result

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
    ) -> bool:
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
            return _filter_converter_config(config)
        case _:
            raise TypeError("Unsupported Type")


def add_prefix(polarion_type: str, prefix: str) -> str:
    """Add a prefix to the given ``polarion_type``."""
    if prefix:
        return f"{prefix}_{polarion_type}"
    return polarion_type


def _filter_converter_config(
    config: dict[str, dict[str, t.Any]]
) -> dict[str, dict[str, t.Any]]:
    custom_converters = (
        "include_pre_and_post_condition",
        "linked_text_as_description",
        "add_context_diagram",
        "add_tree_diagram",
        "add_jinja_fields",
        "jinja_as_description",
    )
    filtered_config = {}
    for name, params in config.items():
        params = params or {}
        if name not in custom_converters:
            logger.error("Unknown converter in config %r", name)
            continue

        if name in ("add_context_diagram", "add_tree_diagram"):
            params = _filter_context_diagram_config(params)

        filtered_config[name] = params

    return filtered_config


def _filter_context_diagram_config(
    config: dict[str, t.Any]
) -> dict[str, t.Any]:
    converted_filters = []
    for filter_name in config.get("filters", []):
        try:
            converted_filters.append(getattr(context_filters, filter_name))
        except AttributeError:
            logger.error("Unknown diagram filter in config %r", filter_name)

    if converted_filters:
        config["filters"] = converted_filters
    return config


def _filter_links(
    c_type: str, links: list[LinkConfig], is_global: bool = False
) -> list[LinkConfig]:
    c_class: type[m.ModelObject]
    if c_type == "diagram":
        c_class = m.Diagram
    else:
        if not (c_classes := m.find_wrapper(c_type)):
            logger.error("Did not find any matching Wrapper for %r", c_type)
            return links
        c_class = c_classes[0]

    available_links: list[LinkConfig] = []
    for link in links:
        capella_attr = link.capella_attr.split(".")[0]
        is_diagram_elements = capella_attr == DIAGRAM_ELEMENTS_SERIALIZER
        if (
            capella_attr == DESCRIPTION_REFERENCE_SERIALIZER
            or (is_diagram_elements and c_class == m.Diagram)
            or hasattr(c_class, capella_attr)
        ):
            available_links.append(link)
        else:
            if is_global:
                logger.info(
                    "Global link %s is not available on Capella type %s",
                    capella_attr,
                    c_type,
                )
            else:
                logger.error(
                    "Link %s is not available on Capella type %s",
                    capella_attr,
                    c_type,
                )
    return available_links
