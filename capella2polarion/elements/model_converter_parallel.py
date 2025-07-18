# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Parallel implementation of model converter operations."""

from __future__ import annotations

import concurrent.futures
import logging
import threading

import capellambse
import polarion_rest_api_client as polarion_api
from tqdm import tqdm

from capella2polarion import errors
from capella2polarion.connectors import polarion_repo
from capella2polarion.elements import (
    data_session,
    link_converter,
    model_converter,
)

logger = logging.getLogger(__name__)

BackLinksMapping = dict[str, dict[str, list[polarion_api.WorkItemLink]]]
"""Type alias for back-links mapping: work_item_id -> role -> links"""


class ParallelModelConverter(model_converter.ModelConverter):
    """Parallel implementation of ``ModelConverter``."""

    def __init__(
        self,
        capella_model: capellambse.MelodyModel,
        project_id: str,
        *,
        max_workers: int = 4,
        enable_parallel_link_generation: bool = True,
        error_collector: errors.ErrorCollector | None = None,
    ) -> None:
        super().__init__(capella_model, project_id)

        self.parallel_max_workers = max_workers
        self.enable_parallel_link_generation = enable_parallel_link_generation
        self.error_collector = error_collector or errors.ErrorCollector()

    def generate_work_item_links(
        self,
        polarion_data_repo: polarion_repo.PolarionDataRepository,
        generate_grouped_links_custom_fields: bool,
    ) -> None:
        """Generate links for all work items in parallel."""
        if not self.enable_parallel_link_generation:
            logger.info("Using sequential link generation")
            super().generate_work_item_links(
                polarion_data_repo, generate_grouped_links_custom_fields
            )
            return

        work_items = [
            (uuid, converter_data)
            for uuid, converter_data in self.converter_session.items()
            if converter_data.work_item is not None
        ]
        if not work_items:
            logger.info("No work items to process for link generation")
            return

        logger.info(
            "Processing %d work items for link generation in parallel",
            len(work_items),
        )
        try:
            link_serializer = link_converter.LinkSerializer(
                polarion_data_repo,
                self.converter_session,
                self.project_id,
                self.model,
                global_grouped_links=generate_grouped_links_custom_fields,
            )
            self.generate_work_item_links_in_parallel(
                work_items, link_serializer
            )
        except Exception as e:
            logger.error("Parallel link generation failed: %s", e)
            logger.info("Falling back to sequential processing")
            super().generate_work_item_links(
                polarion_data_repo, generate_grouped_links_custom_fields
            )

    def generate_work_item_links_in_parallel(
        self,
        work_items: list[tuple[str, data_session.ConverterData]],
        link_serializer: link_converter.LinkSerializer,
    ) -> None:
        """3-phase parallel implementation of work item link generation.

        Notes
        -----
        The function runs the following 3 phases:
         1. Parallel creation of basic work item links.
         2. Parallel creation of forward grouped link fields with
            thread-safe back-links collection.
         3. Parallel creation of back-link fields using collected
            back-links.
        """
        self._create_links_parallel(work_items, link_serializer)
        back_links = self._create_forward_fields_parallel(
            work_items, link_serializer
        )
        self._create_back_fields_parallel(
            work_items, link_serializer, back_links
        )
        logger.info(
            "Completed parallel link generation for %d work items!",
            len(work_items),
        )

    def _create_links_parallel(
        self,
        work_items: list[tuple[str, data_session.ConverterData]],
        link_serializer: link_converter.LinkSerializer,
    ) -> None:
        total = len(work_items)
        errors: list[tuple[str, Exception]] = []

        def _create_links_safely(
            uuid_data: tuple[str, data_session.ConverterData],
        ) -> str:
            uuid, converter_data = uuid_data
            if converter_data.work_item is None:
                logger.warning("No work item found for UUID %s", uuid)
                return uuid
            try:
                converter_data.work_item.linked_work_items = (
                    link_serializer.create_links_for_work_item(uuid)
                )
            except Exception as e:
                logger.error(
                    "Failed to create links for work item %s: %s", uuid, e
                )
                errors.append((uuid, e))
            return uuid

        with (
            concurrent.futures.ThreadPoolExecutor(
                max_workers=self.parallel_max_workers
            ) as executor,
            tqdm(
                total=total, desc="Creating links", unit="link"
            ) as progress_bar,
        ):
            futures = [
                executor.submit(_create_links_safely, item)
                for item in work_items
            ]
            for future in concurrent.futures.as_completed(futures):
                future.result()
                progress_bar.update(1)

        if errors:
            self.error_collector.add_link_errors(errors)
            logger.warning(
                "Failed to create links for %d work items", len(errors)
            )
            failure_rate = len(errors) / total
            logger.warning(
                "Link creation failure rate: %.1f%%", failure_rate * 100
            )

    def _create_forward_fields_parallel(
        self,
        work_items: list[tuple[str, data_session.ConverterData]],
        link_serializer: link_converter.LinkSerializer,
    ) -> BackLinksMapping:
        total = len(work_items)
        errors: list[tuple[str, Exception]] = []
        back_links_lock = threading.Lock()
        back_links: BackLinksMapping = {}

        def _create_forward_fields_safely(
            uuid_data: tuple[str, data_session.ConverterData],
        ) -> str:
            uuid, converter_data = uuid_data
            try:
                local_back_links: BackLinksMapping = {}
                link_serializer.create_grouped_link_fields(
                    converter_data, local_back_links
                )
                with back_links_lock:
                    for work_item_id, role_links in local_back_links.items():
                        for role, links in role_links.items():
                            wi_back_links = back_links.setdefault(
                                work_item_id, {}
                            )
                            wi_back_links.setdefault(role, []).extend(links)
            except Exception as e:
                logger.error(
                    "Failed to create forward fields for work item %s: %s",
                    uuid,
                    e,
                )
                errors.append((uuid, e))
            return uuid

        with (
            concurrent.futures.ThreadPoolExecutor(
                max_workers=self.parallel_max_workers
            ) as executor,
            tqdm(
                total=total, desc="Creating forward fields", unit="field"
            ) as progress_bar,
        ):
            futures = [
                executor.submit(_create_forward_fields_safely, item)
                for item in work_items
            ]
            for future in concurrent.futures.as_completed(futures):
                future.result()
                progress_bar.update(1)

        if errors:
            self.error_collector.add_link_errors(errors)
            logger.warning(
                "Failed to create forward fields for %d work items",
                len(errors),
            )

        return back_links

    def _create_back_fields_parallel(
        self,
        work_items: list[tuple[str, data_session.ConverterData]],
        link_serializer: link_converter.LinkSerializer,
        back_links: BackLinksMapping,
    ) -> None:
        total = len(work_items)
        errors: list[tuple[str, Exception]] = []

        def _create_back_fields_safely(
            uuid_data: tuple[str, data_session.ConverterData],
        ) -> str:
            uuid, converter_data = uuid_data
            work_item = converter_data.work_item
            try:
                if work_item is None or work_item.id is None:
                    return uuid

                if local_back_links := back_links.get(work_item.id):
                    link_serializer.create_grouped_back_link_fields(
                        work_item, local_back_links
                    )
            except Exception as e:
                logger.error(
                    "Failed to create back fields for work item %s: %s",
                    uuid,
                    e,
                )
                errors.append((uuid, e))
            return uuid

        with (
            concurrent.futures.ThreadPoolExecutor(
                max_workers=self.parallel_max_workers
            ) as executor,
            tqdm(
                total=total, desc="Creating back-link fields", unit="field"
            ) as progress_bar,
        ):
            futures = [
                executor.submit(_create_back_fields_safely, item)
                for item in work_items
            ]
            for future in concurrent.futures.as_completed(futures):
                future.result()
                progress_bar.update(1)

        if errors:
            self.error_collector.add_link_errors(errors)
            logger.warning(
                "Failed to create back fields for %d work items", len(errors)
            )
            failure_rate = len(errors) / total
            logger.warning(
                "Back field creation failure rate: %.1f%%", failure_rate * 100
            )
