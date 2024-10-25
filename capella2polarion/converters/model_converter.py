# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""A module containing the overall model conversion class."""

from __future__ import annotations

import logging
import typing as t

import capellambse
import polarion_rest_api_client as polarion_api

from capella2polarion import data_model
from capella2polarion.connectors import polarion_repo
from capella2polarion.converters import (
    converter_config,
    data_session,
    element_converter,
    link_converter,
)

logger = logging.getLogger(__name__)


class ModelConverter:
    """Class to convert elements of a model and store related data."""

    def __init__(
        self,
        model: capellambse.MelodyModel,
        project_id: str,
    ):
        self.model = model
        self.project_id = project_id

        self.converter_session: data_session.ConverterSession = {}

    def read_model(
        self,
        config: converter_config.ConverterConfig,
    ):
        """Read the model using a given config and diagram_idx."""
        missing_types: set[tuple[str, str, dict[str, t.Any]]] = set()
        for layer, c_type in config.layers_and_types():
            below = getattr(self.model, layer)
            if c_type == "Diagram":
                continue

            objects = self.model.search(c_type, below=below)
            for obj in objects:
                attributes = {
                    "is_actor": getattr(obj, "is_actor", None),
                    "nature": getattr(obj, "nature", None),
                }
                if type_config := config.get_type_config(
                    layer, c_type, **attributes
                ):
                    self.converter_session[obj.uuid] = (
                        data_session.ConverterData(layer, type_config, obj)
                    )
                else:
                    missing_types.add((layer, c_type, attributes))

        if config.diagram_config:
            for d in self.model.diagrams:
                self.converter_session[d.uuid] = data_session.ConverterData(
                    "", config.diagram_config, d
                )

        if missing_types:
            for missing_type in missing_types:
                layer, c_type, attributes = missing_type
                logger.warning(
                    "Capella type %r is configured in layer %r, but not"
                    " for %s.",
                    layer,
                    c_type,
                    ", ".join(f"{k!r}={v!r}" for k, v in attributes.items()),
                )

    def generate_work_items(
        self,
        polarion_data_repo: polarion_repo.PolarionDataRepository,
        generate_links: bool = False,
        generate_attachments: bool = False,
        generate_grouped_links_custom_fields: bool = False,
    ) -> dict[str, data_model.CapellaWorkItem]:
        """Return a work items mapping from model elements for Polarion.

        The dictionary maps Capella UUIDs to ``CapellaWorkItem`` s. In
        addition, it is ensured that neither title nor type are None,
        Links are not created in this step by default.

        Parameters
        ----------
        polarion_data_repo
            The PolarionDataRepository object storing current work item
            data.
        generate_links
            A boolean flag to control linked work item generation.
        generate_attachments
            A boolean flag to control attachments generation. For SVG
            attachments, PNGs are generated and attached automatically.
        generate_grouped_links_custom_fields
            A boolean flag to control grouped links custom fields
            generation.
        """
        serializer = element_converter.CapellaWorkItemSerializer(
            self.model,
            polarion_data_repo,
            self.converter_session,
            generate_attachments,
        )
        work_items = serializer.serialize_all()
        for work_item in work_items:
            assert work_item.title is not None
            assert work_item.type is not None

        if generate_links:
            self.generate_work_item_links(
                polarion_data_repo, generate_grouped_links_custom_fields
            )

        return {wi.uuid_capella: wi for wi in work_items}

    def generate_work_item_links(
        self,
        polarion_data_repo: polarion_repo.PolarionDataRepository,
        generate_grouped_links_custom_fields: bool,
    ):
        """Generate links for all work items and add custom fields for them."""
        back_links: dict[str, dict[str, list[polarion_api.WorkItemLink]]] = {}
        link_serializer = link_converter.LinkSerializer(
            polarion_data_repo,
            self.converter_session,
            self.project_id,
            self.model,
        )
        for uuid, converter_data in self.converter_session.items():
            if converter_data.work_item is None:
                logger.warning(
                    "Expected to find a WorkItem for %s, but there is none",
                    uuid,
                )
                continue

            links = link_serializer.create_links_for_work_item(uuid)
            converter_data.work_item.linked_work_items = links

            if generate_grouped_links_custom_fields:
                link_serializer.create_grouped_link_fields(
                    converter_data, back_links
                )

        for uuid, converter_data in self.converter_session.items():
            if converter_data.work_item is None:
                logger.warning(
                    "Expected to find a WorkItem for %s, but there is none",
                    uuid,
                )
                continue

            if converter_data.work_item.id is None:
                logger.error(
                    "Expected WorkItem to be created before creating "
                    "links: %s.",
                    uuid,
                )
                continue

            if local_back_links := back_links.get(converter_data.work_item.id):
                link_serializer.create_grouped_back_link_fields(
                    converter_data.work_item, local_back_links
                )
