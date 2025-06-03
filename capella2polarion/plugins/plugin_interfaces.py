# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Interfaces to implement custom plugins."""

import abc
import dataclasses
import typing as t

import capellambse

from capella2polarion.connectors import polarion_worker
from capella2polarion.documents import document_config
from capella2polarion.elements import converter_config


@dataclasses.dataclass
class AdditionalAttributes:
    """Click args not directly related to the plugin, but maybe of interest."""

    document_rendering_config: t.TextIO | None
    overwrite_layouts: bool
    overwrite_numbering: bool
    synchronize_config: t.TextIO | None
    force_update: bool
    type_prefix: str
    role_prefix: str
    grouped_links_custom_fields: bool
    generate_figure_captions: bool


class PluginInterface(abc.ABC):
    """A general PluginInterface to be implemented by plugins."""

    def __init__(
        self,
        capella_polarion_worker: polarion_worker.CapellaPolarionWorker,
        model: capellambse.MelodyModel,
        additional_configuration: AdditionalAttributes,
        **kwargs: t.Any,  # pylint: disable=unused-argument # noqa: ARG002
    ):
        self.capella_polarion_worker = capella_polarion_worker
        self.model = model
        self.additional_configuration = additional_configuration
        self._document_configs: None | document_config.DocumentConfigs = None
        self._synchronize_config: None | converter_config.ConverterConfig = (
            None
        )

    @abc.abstractmethod
    def run(self, **kwargs: t.Any) -> None:
        """Run your custom code and send the results to polarion."""

    @property
    def document_config(self) -> document_config.DocumentConfigs:
        if self._document_configs is None:
            assert self.additional_configuration.document_rendering_config, (
                "You must define the document rendering config file path"
            )
            self._document_configs = document_config.read_config_file(
                self.additional_configuration.document_rendering_config,
                self.model,
            )

        return self._document_configs

    @property
    def element_config(self) -> converter_config.ConverterConfig:
        if self._synchronize_config is None:
            assert self.additional_configuration.synchronize_config, (
                "You must define the synchronize config file path"
            )
            self._synchronize_config = converter_config.ConverterConfig()
            self._synchronize_config.read_config_file(
                self.additional_configuration.synchronize_config,
                self.additional_configuration.type_prefix,
                self.additional_configuration.role_prefix,
            )

        return self._synchronize_config
