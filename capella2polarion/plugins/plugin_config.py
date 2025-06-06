# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Plugin configuration classes and functions."""

import typing as t

import pydantic
import yaml


class PluginConfig(pydantic.BaseModel):
    """Configuration for a plugin config."""

    plugin_name: str
    init_args: dict[str, t.Any]
    args: dict[str, t.Any]


def read_config_file(config: t.TextIO) -> list[PluginConfig]:
    """Read a yaml containing a list of PluginConfigs."""
    config_content = yaml.safe_load(config)
    return [PluginConfig(**config_item) for config_item in config_content]
