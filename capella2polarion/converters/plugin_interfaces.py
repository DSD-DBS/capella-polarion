# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Interfaces to implement custom plugins."""
import abc

import capellambse

import capella2polarion.converters.capella_object_renderer
from capella2polarion.connectors import polarion_worker
from capella2polarion.converters import element_converter


class PluginInterface(abc.ABC):
    """A general PluginInterface to be implemented by plugins."""

    def __init__(
        self,
        capella_polarion_worker: polarion_worker.CapellaPolarionWorker,
        model: capellambse.MelodyModel,
    ):
        self.capella_polarion_worker = capella_polarion_worker
        self.model = model

    @abc.abstractmethod
    def run(self, **kwargs):
        """Run your custom code and send the results to polarion."""
        pass


class WorkItemPluginInterface(PluginInterface, abc.ABC):
    """An interface providing functionality from the WorkItemSerializer."""

    def __init__(
        self,
        model: capellambse.MelodyModel,
        generate_figure_captions: bool,
        generate_attachments: bool,
        capella_polarion_worker: polarion_worker.CapellaPolarionWorker,
    ):
        super().__init__(capella_polarion_worker, model)
        self.capella_polarion_worker.load_polarion_work_item_map()
        self.capella_object_renderer = capella2polarion.converters.capella_object_renderer.CapellaObjectRenderer(
            model,
            generate_figure_captions,
            generate_attachments,
            self.capella_polarion_worker.polarion_data_repo,
        )
