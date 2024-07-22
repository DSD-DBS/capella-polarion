# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Module with classes and a loader for document rendering configs."""
import pathlib
import typing as t

import pydantic
import yaml


class DocumentRenderingInstance(pydantic.BaseModel):
    """An instance of a document that should be created in Polarion."""

    polarion_space: str
    polarion_name: str
    polarion_title: str | None = None
    params: dict[str, t.Any] = pydantic.Field(default_factory=dict)


class DocumentRenderingConfig(pydantic.BaseModel):
    """A template config, which can result in multiple Polarion documents."""

    template_directory: str | pathlib.Path
    template: str
    instances: list[DocumentRenderingInstance]


def read_config_file(config: t.TextIO):
    """Read a yaml containing a list of DocumentRenderingConfigs."""
    config_content = yaml.safe_load(config)
    return [DocumentRenderingConfig(**c) for c in config_content]
