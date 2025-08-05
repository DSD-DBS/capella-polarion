# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Parallel implementation of Polarion worker operations."""

from __future__ import annotations

import concurrent.futures
import logging
import threading

import polarion_rest_api_client as polarion_api
import tqdm

from capella2polarion import data_model, errors
from capella2polarion.connectors import polarion_worker
from capella2polarion.elements import data_session

logger = logging.getLogger(__name__)


class ParallelCapellaPolarionWorker(polarion_worker.CapellaPolarionWorker):
    """Parallel implementation of ``CapellaPolarionWorker``."""

    def __init__(
        self,
        params: polarion_worker.PolarionWorkerParams,
        force_update: bool = False,
        *,
        max_workers: int,
        enable_parallel_updates: bool = True,
        enable_batched_operations: bool = False,
        error_collector: errors.ErrorCollector | None = None,
    ) -> None:
        super().__init__(params, force_update)

        self.parallel_max_workers = max_workers
        self.enable_parallel_updates = enable_parallel_updates
        self.enable_batched_operations = enable_batched_operations
        self.error_collector = error_collector or errors.ErrorCollector()

    def compare_and_update_work_items(
        self, converter_session: data_session.ConverterSession
    ) -> None:
        """Update work items in a Polarion project in parallel."""
        work_items = [
            (uuid, data)
            for uuid, data in converter_session.items()
            if uuid in self.polarion_data_repo and data.work_item is not None
        ]

        if not work_items:
            logger.info("No work items to process")
            return

        num_wis = len(work_items)
        if self.enable_batched_operations:
            logger.info(
                "Processing %d work items with batched operations", num_wis
            )
            self._compare_and_update_work_items_batched(work_items)
        elif self.enable_parallel_updates:
            logger.info(
                "Processing %d work items in parallel (max_workers=%d)",
                num_wis,
                self.parallel_max_workers,
            )
            self._compare_and_update_work_items_parallel(work_items)
        else:
            logger.info("Processing %d work items sequentially", num_wis)
            for _, data in work_items:
                self.compare_and_update_work_item(data)

    def _compare_and_update_work_items_parallel(
        self,
        work_items: list[tuple[str, data_session.ConverterData]],
    ) -> None:
        errors: list[tuple[str, Exception]] = []
        errors_lock = threading.Lock()

        def _compare_and_update_work_items_safely(
            uuid: str, data: data_session.ConverterData
        ) -> str:
            try:
                self.compare_and_update_work_item(data)
            except Exception as e:
                logger.error("Failed to update work item %s: %s", uuid, e)
                with errors_lock:
                    errors.append((uuid, e))
            return uuid

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.parallel_max_workers
        ) as executor:
            updates = [
                executor.submit(
                    _compare_and_update_work_items_safely, uuid, data
                )
                for uuid, data in work_items
            ]
            with tqdm.tqdm(
                total=len(work_items),
                desc="Updating work items",
                unit="work item",
            ) as progress_bar:
                for future in concurrent.futures.as_completed(updates):
                    future.result()
                    progress_bar.update(1)

            if errors:
                logger.warning(
                    "Failed to update %d out of %d work items",
                    len(errors),
                    len(work_items),
                )
                for uuid, error in errors:
                    self.error_collector.add_work_item_error(uuid, error)
                    logger.error("Work item %s: %s", uuid, error)

                failure_rate = len(errors) / len(work_items)
                logger.warning(
                    "Work item update failure rate: %.1f%%", failure_rate * 100
                )
            else:
                logger.info(
                    "Successfully updated all %d work items", len(work_items)
                )

    def _compare_and_update_work_items_batched(
        self,
        work_items: list[tuple[str, data_session.ConverterData]],
    ) -> None:
        logger.info("Phase 1: Analyzing work items for batch operations")

        def analyze_work_item(
            item_data: tuple[str, data_session.ConverterData],
        ) -> data_model.WorkItemAnalysis:
            uuid, data = item_data
            try:
                return self._analyze_work_item_changes(data)
            except Exception as e:
                logger.error("Failed to analyze work item %s: %s", uuid, e)
                assert data.work_item is not None
                return data_model.WorkItemAnalysis(
                    uuid=uuid, work_item=data.work_item, error=e
                )

        analysis_results: list[data_model.WorkItemAnalysis] = []
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.parallel_max_workers
        ) as executor:
            analysis_futures = [
                executor.submit(analyze_work_item, item_data)
                for item_data in work_items
            ]
            total = len(analysis_futures)
            with tqdm.tqdm(
                total=total, desc="Analyzing work items", unit="work item"
            ) as progress_bar:
                for future in concurrent.futures.as_completed(
                    analysis_futures
                ):
                    result = future.result()
                    analysis_results.append(result)
                    progress_bar.update(1)

        logger.info("Phase 2: Executing batched operations")
        try:
            self._execute_batched_operations(analysis_results)
        except Exception as e:
            logger.error("Batched operations failed: %s", e)
            logger.info("Falling back to parallel processing")
            self._compare_and_update_work_items_parallel(work_items)

    def _analyze_work_item_changes(
        self, data: data_session.ConverterData
    ) -> data_model.WorkItemAnalysis:
        """Analyze what changes are needed for a work item."""
        new = data.work_item
        assert new is not None
        uuid = new.uuid_capella
        old = self.polarion_data_repo.get_work_item_by_capella_uuid(uuid)
        assert old is not None
        assert old.id is not None

        return self._analyze_work_item_for_update(new, old)

    def _execute_batched_operations(
        self, analysis_results: list[data_model.WorkItemAnalysis]
    ) -> None:
        successful_analyses = self._filter_and_handle_failed_analyses(
            analysis_results
        )
        batch_data = self._prepare_batch_operations(successful_analyses)
        self._execute_batch_updates(batch_data)
        logger.info(
            "Successfully completed batched operations for %d work items",
            len(successful_analyses),
        )

    def _filter_and_handle_failed_analyses(
        self, analysis_results: list[data_model.WorkItemAnalysis]
    ) -> list[data_model.WorkItemAnalysis]:
        successful_analyses = [a for a in analysis_results if a.error is None]
        failed_analyses = [a for a in analysis_results if a.error is not None]
        if failed_analyses:
            logger.warning(
                "Skipping %d work items due to analysis errors",
                len(failed_analyses),
            )
            for analysis in failed_analyses:
                assert analysis.error is not None
                self.error_collector.add_work_item_error(
                    analysis.uuid, analysis.error
                )

        return successful_analyses

    def _prepare_batch_operations(
        self, successful_analyses: list[data_model.WorkItemAnalysis]
    ) -> dict[str, list]:
        type_updates: list[data_model.CapellaWorkItem] = []
        work_item_updates: list[data_model.CapellaWorkItem] = []
        all_links_to_delete: list[polarion_api.WorkItemLink] = []
        all_links_to_create: list[polarion_api.WorkItemLink] = []
        total = len(successful_analyses)
        with tqdm.tqdm(
            total=total, desc="Analyzing operations", unit="operation"
        ) as progress_bar:
            for analysis in successful_analyses:
                if not analysis.needs_update:
                    continue

                assert analysis.old_work_item is not None
                if analysis.needs_type_update:
                    type_update = self._create_type_update(analysis)
                    type_updates.append(type_update)
                    analysis.work_item.type = None

                if analysis.work_item_changed or self.force_update:
                    self._prepare_work_item_for_update(analysis)
                    work_item_updates.append(analysis.work_item)
                else:
                    self._clear_work_item_attributes(analysis)
                    work_item_updates.append(analysis.work_item)

                if analysis.links_to_delete:
                    all_links_to_delete.extend(
                        analysis.links_to_delete.values()
                    )
                if analysis.links_to_create:
                    all_links_to_create.extend(
                        analysis.links_to_create.values()
                    )

                progress_bar.update(1)

        return {
            "type_updates": type_updates,
            "work_item_updates": work_item_updates,
            "links_to_delete": all_links_to_delete,
            "links_to_create": all_links_to_create,
        }

    def _create_type_update(
        self, analysis: data_model.WorkItemAnalysis
    ) -> data_model.CapellaWorkItem:
        assert analysis.old_work_item is not None
        assert analysis.old_work_item.id is not None
        return data_model.CapellaWorkItem(
            id=analysis.old_work_item.id, type=analysis.work_item.type
        )

    def _prepare_work_item_for_update(
        self, analysis: data_model.WorkItemAnalysis
    ) -> None:
        assert analysis.old_work_item is not None
        if (
            analysis.old_work_item.attachments
            or analysis.work_item.attachments
        ):
            self._handle_attachments(analysis)

        if analysis.work_item.attachments:
            self._refactor_attached_images(analysis.work_item)

        self._clean_uuid_attributes(analysis)
        self._handle_additional_attributes(analysis)
        analysis.work_item.status = "open"

    def _clear_work_item_attributes(
        self, analysis: data_model.WorkItemAnalysis
    ) -> None:
        analysis.work_item.clear_attributes()
        analysis.work_item.type = None
        analysis.work_item.status = None
        analysis.work_item.description = None
        analysis.work_item.title = None

    def _handle_attachments(
        self, analysis: data_model.WorkItemAnalysis
    ) -> None:
        assert analysis.old_work_item is not None
        try:
            old_attachments = []
            if analysis.old_work_item.attachments:
                old_attachments = (
                    self.project_client.work_items.attachments.get_all(
                        work_item_id=analysis.old_work_item.id
                    )
                )

            attachment_changed = self.update_attachments(
                analysis.work_item,
                analysis.old_work_item.attachment_checksums,
                analysis.work_item.attachment_checksums,
                old_attachments,
            )
            analysis.work_item_changed |= attachment_changed
        except Exception as e:
            logger.error(
                "Failed to update attachments for %s: %s",
                analysis.uuid,
                e,
            )

    def _clean_uuid_attributes(
        self, analysis: data_model.WorkItemAnalysis
    ) -> None:
        assert analysis.old_work_item is not None

        del analysis.work_item.additional_attributes["uuid_capella"]
        del analysis.old_work_item.additional_attributes["uuid_capella"]

    def _handle_additional_attributes(
        self, analysis: data_model.WorkItemAnalysis
    ) -> None:
        assert analysis.old_work_item is not None
        defaults = polarion_worker.DEFAULT_ATTRIBUTE_VALUES
        for (
            attribute,
            value,
        ) in analysis.old_work_item.additional_attributes.items():
            if attribute not in analysis.work_item.additional_attributes:
                analysis.work_item.additional_attributes[attribute] = (
                    defaults.get(type(value))
                )
            elif analysis.work_item.additional_attributes[attribute] == value:
                del analysis.work_item.additional_attributes[attribute]

    def _execute_batch_updates(self, batch_data: dict[str, list]) -> None:
        type_updates = batch_data["type_updates"]
        work_item_updates = batch_data["work_item_updates"]
        links_to_delete = batch_data["links_to_delete"]
        links_to_create = batch_data["links_to_create"]
        total_operations = (
            (1 if type_updates else 0)
            + (1 if work_item_updates else 0)
            + (1 if links_to_delete else 0)
            + (1 if links_to_create else 0)
        )

        with tqdm.tqdm(
            total=total_operations,
            desc="Executing batch operations",
            unit="batches",
        ) as progress_bar:
            if type_updates:  # 1. Type updates first (must be separate)
                logger.info(
                    "Batch updating types for %d work items", len(type_updates)
                )
                self.project_client.work_items.update(type_updates)
                progress_bar.update(1)

            if work_item_updates:  # 2. Main work item updates
                logger.info(
                    "Batch updating %d work items", len(work_item_updates)
                )
                self.project_client.work_items.update(work_item_updates)
                progress_bar.update(1)

            if links_to_delete:  # 3. Delete old links
                logger.info("Batch deleting %d links", len(links_to_delete))
                self.project_client.work_items.links.delete(links_to_delete)
                progress_bar.update(1)

            if links_to_create:  # 4. Create new links
                logger.info("Batch creating %d links", len(links_to_create))
                self.project_client.work_items.links.create(links_to_create)
                progress_bar.update(1)
