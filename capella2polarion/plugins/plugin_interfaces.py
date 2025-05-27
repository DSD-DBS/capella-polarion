# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Interfaces to implement custom plugins."""
import abc
import dataclasses
import typing as t

import capellambse

from capella2polarion.connectors import polarion_worker


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
        **kwargs,  # pylint: disable=unused-argument
    ):
        self.capella_polarion_worker = capella_polarion_worker
        self.model = model
        self.additional_configuration = additional_configuration

    @abc.abstractmethod
    def run(self, **kwargs):
        """Run your custom code and send the results to polarion."""
