# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module providing capella2polarion config class using Pydantic."""

from __future__ import annotations

import logging
import re
import typing as t
from collections import abc as cabc

import pydantic
import yaml
from capellambse import model as m

from capella2polarion.data_model import converter_config as cc

logger = logging.getLogger(__name__)

DESCRIPTION_REFERENCE_SERIALIZER = "description_reference"
DIAGRAM_ELEMENTS_SERIALIZER = "diagram_elements"


def add_prefix(base_id: str, prefix: str) -> str:
    """Add a prefix to the given base_id, avoiding double underscores."""
    if prefix and base_id:
        prefix = prefix.rstrip("_")
        base_id = base_id.lstrip("_")
        return f"{prefix}_{base_id}"
    return base_id


def _default_type_conversion(c_type: str) -> str:
    if not c_type:
        return ""
    return c_type[0].lower() + c_type[1:]


class ConverterConfig:
    """Orchestrates configuration loading and access using Pydantic models."""

    def __init__(self):
        self._layer_configs: dict[
            str, dict[str, list[cc.CapellaTypeConfigProcessed]]
        ] = {}
        self._global_type_configs: dict[str, cc.CapellaTypeConfigProcessed] = (
            {}
        )
        self.diagram_config: cc.CapellaTypeConfigProcessed | None = None
        self._default_config: cc.CapellaTypeConfigProcessed | None = None
        self.polarion_types: set[str] = set()
        self.base_serializers = list(cc.SERIALIZER_PARAM_MODELS.keys())
        self.serializer_pattern = re.compile(
            rf"^({'|'.join(re.escape(s) for s in self.base_serializers)})(?:-[a-zA-Z0-9_]+)?$"
        )

    def read_config_file(
        self,
        synchronize_config: t.TextIO | str,
        type_prefix: str = "",
        role_prefix: str = "",
    ):
        """Parse config and process it into internal structure.

        Parameters
        ----------
        synchronize_config
            An open file handle or file path string for the YAML config.
        type_prefix
            A prefix to add to all derived Polarion type IDs.
        role_prefix
            A prefix to add to all derived Polarion link role IDs.

        Raises
        ------
        ValueError
            If the configuration file has syntax errors, validation errors,
            or structural problems.
        """
        try:
            raw_config_dict = yaml.safe_load(synchronize_config)
            parsed_config_root = cc.FullConfigInput.model_validate(
                raw_config_dict
            ).root
        except (
            yaml.YAMLError,
            pydantic.ValidationError,
            TypeError,
            ValueError,
        ) as e:
            logger.exception(
                "Failed to load or validate configuration file: %s", e
            )
            raise ValueError(f"Configuration error: {e}") from e

        self._current_type_prefix = type_prefix
        self._current_role_prefix = role_prefix

        global_layer_config = parsed_config_root.pop("*", {})
        global_type_defaults_list = global_layer_config.pop("*", [])
        if len(global_type_defaults_list) > 1:
            logger.warning(
                "Multiple configurations found for '*.*', using the first one."
            )

        default_input = (
            global_type_defaults_list[0]
            if global_type_defaults_list
            else cc.CapellaTypeConfigInput()
        )
        self._default_config = self._process_single_config_input(
            default_input, c_type="*", parent_config=None
        )
        if self._default_config:
            self._default_config.p_type = ""

        diagram_input_list = global_layer_config.pop("Diagram", [])
        if len(diagram_input_list) > 1:
            logger.warning(
                "Multiple configurations found for '*.Diagram',"
                " using the first one.",
            )

        diagram_input = (
            diagram_input_list[0]
            if diagram_input_list
            else cc.CapellaTypeConfigInput()
        )
        self.diagram_config = self._process_single_config_input(
            diagram_input, c_type="Diagram", parent_config=self._default_config
        )
        if self.diagram_config and self.diagram_config.p_type:
            self.polarion_types.add(self.diagram_config.p_type)

        for c_type, type_input_list in global_layer_config.items():
            if len(type_input_list) > 1:
                logger.warning(
                    "Multiple global configurations found for type '%s',"
                    " using the first one.",
                    c_type,
                )
            type_input = type_input_list[0]
            processed_global = self._process_single_config_input(
                type_input, c_type=c_type, parent_config=self._default_config
            )
            if processed_global:
                self._global_type_configs[c_type] = processed_global
                if processed_global.p_type:
                    self.polarion_types.add(processed_global.p_type)

        for layer, layer_types_dict in parsed_config_root.items():
            self._layer_configs[layer] = {}
            for c_type, type_input_list in layer_types_dict.items():
                parent_config = self._global_type_configs.get(
                    c_type, self._default_config
                )
                processed_list: list[cc.CapellaTypeConfigProcessed] = []
                for type_input in type_input_list:
                    processed = self._process_single_config_input(
                        type_input, c_type=c_type, parent_config=parent_config
                    )
                    if processed:
                        processed_list.append(processed)
                        if processed.p_type:
                            self.polarion_types.add(processed.p_type)
                processed_list.sort(
                    key=lambda c: (
                        c.nature_specifier is not None,
                        c.is_actor_specifier is not None,
                    ),
                    reverse=True,
                )
                self._layer_configs[layer][c_type] = processed_list

        del self._current_type_prefix
        del self._current_role_prefix

    def _process_single_config_input(
        self,
        config_input: cc.CapellaTypeConfigInput,
        c_type: str,
        parent_config: cc.CapellaTypeConfigProcessed | None,
    ) -> cc.CapellaTypeConfigProcessed | None:
        parent_links = parent_config.links if parent_config else []
        parent_converters = parent_config.converters if parent_config else {}
        parent_p_type = parent_config.p_type if parent_config else None

        current_links_processed: list[cc.LinkConfigProcessed] = []
        for link_in in config_input.links:
            processed_link = cc.LinkConfigProcessed.model_validate(link_in)
            assert processed_link.polarion_role is not None
            processed_link.polarion_role = add_prefix(
                processed_link.polarion_role, self._current_role_prefix
            )
            current_links_processed.append(processed_link)

        combined_links_map: dict[str, cc.LinkConfigProcessed] = {}
        for link in current_links_processed:
            combined_links_map[link.capella_attr] = link

        for link in parent_links:
            if link.capella_attr not in combined_links_map:
                parent_link_copy = link.model_copy(deep=True)
                combined_links_map[link.capella_attr] = parent_link_copy

        final_links = self._filter_links_semantically(
            c_type, list(combined_links_map.values())
        )

        serializer_input = config_input.serializer or {}
        if not isinstance(serializer_input, dict):
            logger.error(
                "Internal error: Serializer input was not normalized to a "
                "dict for %s",
                c_type,
            )
            current_converters = {}
        else:
            current_converters = self._process_serializer_dict(
                serializer_input
            )

        final_converters = {
            k: v.model_copy(deep=True) for k, v in parent_converters.items()
        }
        for k, v in current_converters.items():
            final_converters[k] = (
                v.model_copy(deep=True) if isinstance(v, cc.BaseModel) else v
            )

        p_type_raw = config_input.polarion_type or parent_p_type
        if not p_type_raw and c_type not in ("*", "Diagram"):
            p_type_raw = _default_type_conversion(c_type)

        final_p_type = ""
        if p_type_raw:
            final_p_type = add_prefix(p_type_raw, self._current_type_prefix)
        return cc.CapellaTypeConfigProcessed(
            p_type=final_p_type,
            converters=final_converters,
            links=final_links,
            is_actor_specifier=config_input.is_actor,
            nature_specifier=config_input.nature,
        )

    def _process_serializer_dict(
        self, raw_serializers: dict[str, t.Any]
    ) -> dict[str, cc.BaseModel]:
        processed_serializers: dict[str, cc.BaseModel] = {}
        for name, params in raw_serializers.items():
            match = self.serializer_pattern.match(name)
            if not match:
                logger.error(
                    "Unknown or invalid serializer format in config: %r", name
                )
                continue
            base_name = match.group(1)
            param_model = cc.SERIALIZER_PARAM_MODELS.get(base_name)
            if not param_model:
                logger.warning(
                    "No parameter model defined for base serializer %r (from %r).",
                    base_name,
                    name,
                )
                continue

            validated_params = param_model.model_validate(params or {})
            processed_serializers[name] = validated_params
        return processed_serializers

    def _filter_links_semantically(
        self,
        c_type: str,
        links: list[cc.LinkConfigProcessed],
    ) -> list[cc.LinkConfigProcessed]:
        if c_type in ("*",):
            return links
        if c_type == "Diagram":
            available_links: list[cc.LinkConfigProcessed] = []
            for link in links:
                if link.capella_attr in (
                    DIAGRAM_ELEMENTS_SERIALIZER,
                    DESCRIPTION_REFERENCE_SERIALIZER,
                ):
                    available_links.append(link)
                else:
                    logger.warning(
                        "Link attribute %r is not available on Capella type %s. Link ignored.",
                        link.capella_attr,
                        c_type,
                    )
            return available_links
        try:
            c_classes = m.find_wrapper(c_type)
            if not c_classes:
                logger.error(
                    "Capella type %r not found by capellambse.find_wrapper. Cannot verify links.",
                    c_type,
                )
                return []
            c_class = c_classes[0]
        except Exception as e:
            logger.exception(
                "Error calling capellambse.find_wrapper for type %r: %s",
                c_type,
                e,
            )
            return []
        available_links = []
        for link in links:
            capella_attr_base = link.capella_attr.split(".")[0]
            is_special_serializer = capella_attr_base in (
                DESCRIPTION_REFERENCE_SERIALIZER,
                DIAGRAM_ELEMENTS_SERIALIZER,
            )
            if is_special_serializer or hasattr(c_class, capella_attr_base):
                available_links.append(link)
            else:
                logger.warning(
                    "Link attribute %r is not available on Capella type %s. Link ignored.",
                    capella_attr_base,
                    c_type,
                )
        return available_links

    def get_type_config(
        self, layer: str, c_type: str, **attributes: t.Any
    ) -> cc.CapellaTypeConfigProcessed | None:
        """Return most specific matching type config.

        Searches layer-specific configurations first, then global type
        configurations, and finally falls back to the default
        configuration. Matching considers attributes like ``is_actor``
        and ``nature``.

        Parameters
        ----------
        layer
            The Capella layer name (e.g., "oa", "sa").
        c_type
            The Capella type name (e.g., "Class", "SystemFunction").
        **attributes
            Keyword arguments used for matching (e.g., ``is_actor=True``).

        Returns
        -------
        type_config
            The matching type configuration or None if no configuration
            matches.
        """
        layer_configs = self._layer_configs.get(layer, {}).get(c_type, [])
        for config in layer_configs:
            if self._config_matches(config, **attributes):
                return config.model_copy(deep=True)
        if global_config := self._global_type_configs.get(c_type):
            if self._config_matches(global_config, **attributes):
                return global_config.model_copy(deep=True)
        if self._default_config:
            default_copy = self._default_config.model_copy(deep=True)
            if not default_copy.p_type and c_type not in ("*", "Diagram"):
                p_type_raw = _default_type_conversion(c_type)
                type_prefix = getattr(self, "_current_type_prefix", "")
                default_copy.p_type = add_prefix(p_type_raw, type_prefix)
            return default_copy
        return None

    def _config_matches(
        self,
        config: cc.CapellaTypeConfigProcessed,
        **kwargs: t.Any,
    ) -> bool:
        for attr_name, expected_value in kwargs.items():
            actor_config_value: bool | None = None
            nature_config_value: str | None = None
            if attr_name == "is_actor":
                actor_config_value = config.is_actor_specifier
                if (
                    actor_config_value is not None
                    and actor_config_value != expected_value
                ):
                    return False
            elif attr_name == "nature":
                nature_config_value = config.nature_specifier
                if (
                    nature_config_value is not None
                    and nature_config_value != expected_value
                ):
                    return False
        return True

    def __contains__(self, item: tuple[str, str, dict[str, t.Any]]) -> bool:
        """Check if there is a config.

        Parameters
        ----------
        item
            A tuple containing:
              - layer_name
              - capella_type_name
              - attributes_dict

        Returns
        -------
        contained
            True if a configuration is found, False otherwise.
        """
        try:
            layer, c_type, attributes = item
            return (
                self.get_type_config(layer, c_type, **attributes) is not None
            )
        except (TypeError, IndexError, ValueError):
            return False

    def layers_and_types(self) -> cabc.Iterator[tuple[str, str]]:
        """Yield unique layer/type combinations present in the config."""
        seen = set()
        for layer, layer_types in self._layer_configs.items():
            for c_type in layer_types:
                if (layer, c_type) not in seen:
                    yield layer, c_type
                    seen.add((layer, c_type))
        all_layers = set(self._layer_configs.keys())
        for layer in all_layers:
            layer_types = self._layer_configs.get(layer, {})
            for c_type in self._global_type_configs:
                if c_type not in layer_types and (layer, c_type) not in seen:
                    yield layer, c_type
                    seen.add((layer, c_type))
