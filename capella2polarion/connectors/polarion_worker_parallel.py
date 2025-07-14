# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Parallel implementation of Polarion worker operations."""

from __future__ import annotations

import concurrent.futures
import logging
import os

import polarion_rest_api_client as polarion_api

from capella2polarion import data_model
from capella2polarion.connectors import polarion_worker
from capella2polarion.elements import data_session

logger = logging.getLogger(__name__)

MAX_FAILURE_THRESHOLD = 0.1
"""Maximum rate of failed work items during serialization."""


class ParallelCapellaPolarionWorker(polarion_worker.CapellaPolarionWorker):
    """Parallel implementation of Capella-Polarion worker operations."""

    def __init__(
        self,
        params: polarion_worker.PolarionWorkerParams,
        force_update: bool = False,
        *,
        max_workers: int | None = None,
        parallel_threshold: int = 5,
        enable_parallel_updates: bool = True,
        enable_batched_operations: bool = False,
    ) -> None:
        super().__init__(params, force_update)

        self.parallel_max_workers = max_workers or min(8, os.cpu_count() or 4)
        self.parallel_threshold = parallel_threshold
        self.enable_parallel_updates = enable_parallel_updates
        self.enable_batched_operations = enable_batched_operations

    def compare_and_update_work_items(
        self, converter_session: data_session.ConverterSession
    ) -> None:
        """Update work items in a Polarion project in parallel."""
        work_items_to_process = [
            (uuid, data)
            for uuid, data in converter_session.items()
            if uuid in self.polarion_data_repo and data.work_item is not None
        ]

        if not work_items_to_process:
            logger.info("No work items to process")
            return

        if (
            self.enable_batched_operations
            and len(work_items_to_process) >= self.parallel_threshold
            and self.enable_batched_operations
        ):
            logger.info(
                "Processing %d work items with batched operations",
                len(work_items_to_process),
            )
            self._compare_and_update_work_items_batched(work_items_to_process)
        elif (
            self.enable_parallel_updates
            and len(work_items_to_process) >= self.parallel_threshold
        ):
            logger.info(
                "Processing %d work items in parallel (max_workers=%d)",
                len(work_items_to_process),
                self.parallel_max_workers,
            )
            self._compare_and_update_work_items_parallel(work_items_to_process)
        else:
            logger.info(
                "Processing %d work items sequentially",
                len(work_items_to_process),
            )
            self._compare_and_update_work_items_sequential(
                work_items_to_process
            )

    def _compare_and_update_work_items_sequential(
        self,
        work_items_to_process: list[tuple[str, data_session.ConverterData]],
    ) -> None:
        """Sequential implementation using ``CapellaPolarionWorker``."""
        for _, data in work_items_to_process:
            self.compare_and_update_work_item(data)

    def _compare_and_update_work_items_parallel(
        self,
        work_items_to_process: list[tuple[str, data_session.ConverterData]],
    ) -> None:
        """Process work items in parallel with comprehensive error handling."""

        def process_work_item(
            item_data: tuple[str, data_session.ConverterData],
        ) -> tuple[str, Exception | None]:
            """Process a single work item with error handling."""
            uuid, data = item_data
            try:
                self.compare_and_update_work_item(data)
                return uuid, None
            except Exception as e:
                logger.error("Failed to update work item %s: %s", uuid, e)
                return uuid, e

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.parallel_max_workers
        ) as executor:
            future_to_uuid = {
                executor.submit(process_work_item, item_data): item_data[0]
                for item_data in work_items_to_process
            }

            errors: list[tuple[str, Exception]] = []
            completed: int = 0
            for future in concurrent.futures.as_completed(future_to_uuid):
                uuid = future_to_uuid[future]
                try:
                    result_uuid, error = future.result()
                    if error:
                        errors.append((result_uuid, error))
                    completed += 1

                    if completed % 10 == 0:
                        logger.info(
                            "Processed %d/%d work items",
                            completed,
                            len(work_items_to_process),
                        )

                except Exception as e:
                    logger.error(
                        "Unexpected error processing work item %s: %s", uuid, e
                    )
                    errors.append((uuid, e))

            if errors:
                logger.warning(
                    "Failed to update %d out of %d work items",
                    len(errors),
                    len(work_items_to_process),
                )
                for uuid, error in errors:
                    logger.error("Work item %s: %s", uuid, error)

                failure_rate = len(errors) / len(work_items_to_process)
                if failure_rate > MAX_FAILURE_THRESHOLD:
                    raise RuntimeError(
                        f"Too many work item update failures: {failure_rate * 100}%"
                    )
            else:
                logger.info(
                    "Successfully updated all %d work items",
                    len(work_items_to_process),
                )

    def _compare_and_update_work_items_batched(
        self,
        work_items_to_process: list[tuple[str, data_session.ConverterData]],
    ) -> None:
        """Process work items using batched operations for better API efficiency."""
        logger.info("Phase 1: Analyzing work items for batch operations")

        def analyze_work_item(
            item_data: tuple[str, data_session.ConverterData],
        ) -> data_model.WorkItemAnalysis:
            """Analyze what operations are needed for a work item."""
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
                for item_data in work_items_to_process
            ]

            for future in concurrent.futures.as_completed(analysis_futures):
                result = future.result()
                analysis_results.append(result)

        logger.info("Phase 2: Executing batched operations")
        try:
            self._execute_batched_operations(analysis_results)
        except Exception as e:
            logger.error("Batched operations failed: %s", e)
            logger.info("Falling back to parallel processing")
            self._compare_and_update_work_items_parallel(work_items_to_process)

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

        analysis = data_model.WorkItemAnalysis(
            uuid=uuid, work_item=new, old_work_item=old
        )
        analysis.needs_update = self.needs_work_item_update(new, old)
        if not analysis.needs_update:
            return analysis

        analysis.work_item_changed = (
            new.content_checksum != old.content_checksum
        )
        analysis.needs_type_update = new.type != old.type
        if analysis.work_item_changed or self.force_update:
            fresh_old = self.project_client.work_items.get(
                old.id, work_item_cls=data_model.CapellaWorkItem
            )
            assert fresh_old is not None
            analysis.old_work_item = fresh_old
            if fresh_old.attachments or new.attachments:
                try:
                    attachment_changed = (
                        fresh_old.attachment_checksums
                        != new.attachment_checksums
                    )
                    analysis.work_item_changed |= attachment_changed
                except Exception as e:
                    logger.error(
                        "Failed to check attachments for %s: %s",
                        analysis.uuid,
                        e,
                    )

            if fresh_old.linked_work_items_truncated:
                fresh_old.linked_work_items = (
                    self.project_client.work_items.links.get_all(fresh_old.id)
                )

            analysis.links_to_delete = self.get_missing_link_ids(
                fresh_old.linked_work_items, new.linked_work_items
            )
            analysis.links_to_create = self.get_missing_link_ids(
                new.linked_work_items, fresh_old.linked_work_items
            )

        return analysis

    def _execute_batched_operations(
        self, analysis_results: list[data_model.WorkItemAnalysis]
    ) -> None:
        """Execute operations in batches for better API efficiency."""
        successful_analyses = [a for a in analysis_results if a.error is None]
        failed_analyses = [a for a in analysis_results if a.error is not None]
        if failed_analyses:
            logger.warning(
                "Skipping %d work items due to analysis errors",
                len(failed_analyses),
            )

        type_updates: list[data_model.CapellaWorkItem] = []
        work_item_updates: list[data_model.CapellaWorkItem] = []
        all_links_to_delete: list[polarion_api.WorkItemLink] = []
        all_links_to_create: list[polarion_api.WorkItemLink] = []
        for analysis in successful_analyses:
            if not analysis.needs_update:
                continue

            assert analysis.old_work_item is not None

            if analysis.needs_type_update:
                assert analysis.old_work_item.id is not None
                type_update = data_model.CapellaWorkItem(
                    id=analysis.old_work_item.id, type=analysis.work_item.type
                )
                type_updates.append(type_update)
                analysis.work_item.type = None

            if analysis.work_item_changed or self.force_update:
                if (
                    analysis.old_work_item.attachments
                    or analysis.work_item.attachments
                ):
                    try:
                        old_attachments = []
                        if analysis.old_work_item.attachments:
                            old_attachments = self.project_client.work_items.attachments.get_all(
                                work_item_id=analysis.old_work_item.id
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

                if analysis.work_item.attachments:
                    self._refactor_attached_images(analysis.work_item)

                del analysis.work_item.additional_attributes["uuid_capella"]
                del analysis.old_work_item.additional_attributes[
                    "uuid_capella"
                ]

                defaults = polarion_worker.DEFAULT_ATTRIBUTE_VALUES
                for (
                    attribute,
                    value,
                ) in analysis.old_work_item.additional_attributes.items():
                    if (
                        attribute
                        not in analysis.work_item.additional_attributes
                    ):
                        analysis.work_item.additional_attributes[attribute] = (
                            defaults.get(type(value))
                        )
                    elif (
                        analysis.work_item.additional_attributes[attribute]
                        == value
                    ):
                        del analysis.work_item.additional_attributes[attribute]

                analysis.work_item.status = "open"
                work_item_updates.append(analysis.work_item)
            else:
                analysis.work_item.clear_attributes()
                analysis.work_item.type = None
                analysis.work_item.status = None
                analysis.work_item.description = None
                analysis.work_item.title = None
                work_item_updates.append(analysis.work_item)

            if analysis.links_to_delete:
                all_links_to_delete.extend(analysis.links_to_delete.values())
            if analysis.links_to_create:
                all_links_to_create.extend(analysis.links_to_create.values())

        try:  # Execute batch operations in proper order
            if type_updates:  # 1. Type updates first (must be separate)
                logger.info(
                    "Batch updating types for %d work items", len(type_updates)
                )
                self.project_client.work_items.update(type_updates)

            if work_item_updates:  # 2. Main work item updates
                logger.info(
                    "Batch updating %d work items", len(work_item_updates)
                )
                self.project_client.work_items.update(work_item_updates)

            if all_links_to_delete:  # 3. Delete old links
                logger.info(
                    "Batch deleting %d links", len(all_links_to_delete)
                )
                self.project_client.work_items.links.delete(
                    all_links_to_delete
                )

            if all_links_to_create:  # 4. Create new links
                logger.info(
                    "Batch creating %d links", len(all_links_to_create)
                )
                self.project_client.work_items.links.create(
                    all_links_to_create
                )

            logger.info(
                "Successfully completed batched operations for %d work items",
                len(successful_analyses),
            )

        except polarion_api.PolarionApiException as error:
            logger.error("Batch operations failed: %s", error)
            raise error
