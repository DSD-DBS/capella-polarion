# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Parallel implementation of element converter operations."""

from __future__ import annotations

import concurrent.futures
import logging
import threading
import typing as t

from tqdm import tqdm

from capella2polarion import data_model, errors
from capella2polarion.elements import element_converter

logger = logging.getLogger(__name__)


class ParallelCapellaWorkItemSerializer(
    element_converter.CapellaWorkItemSerializer
):
    """Parallel implementation of ``CapellaWorkItemSerializer``."""

    def __init__(
        self,
        *args: t.Any,
        max_workers: int = 4,
        enable_parallel_serialization: bool = True,
        error_collector: errors.ErrorCollector | None = None,
        **kwargs: t.Any,
    ) -> None:
        super().__init__(*args, **kwargs)

        self.parallel_max_workers = max_workers
        self.enable_parallel_serialization = enable_parallel_serialization
        self.error_collector = error_collector or errors.ErrorCollector()

    def serialize_all(self) -> list[data_model.CapellaWorkItem]:
        """Serialize all items with optional parallel processing."""
        if not self.enable_parallel_serialization:
            logger.info("Using sequential serialization")
            return super().serialize_all()

        uuids = list(self.converter_session)
        if not uuids:
            logger.info("No work items to serialize")
            return []

        logger.info(
            "Processing %d work items for serialization in parallel",
            len(uuids),
        )

        try:
            return self._serialize_all_parallel(uuids)
        except Exception as e:
            logger.error("Parallel serialization failed: %s", e)
            logger.info("Falling back to sequential processing")
            return super().serialize_all()

    def _serialize_all_parallel(
        self, uuids: list[str]
    ) -> list[data_model.CapellaWorkItem]:
        """Parallelize work item serialization using ThreadPoolExecutor."""
        errors: list[tuple[str, Exception]] = []
        errors_lock = threading.Lock()
        all_work_items: list[data_model.CapellaWorkItem] = []

        def _serialize_single_safely(
            uuid: str,
        ) -> data_model.CapellaWorkItem | None:
            """Safely serialize a single UUID with error handling."""
            try:
                return self.serialize(uuid)
            except Exception as e:
                logger.error("Failed to serialize work item %s: %s", uuid, e)
                with errors_lock:
                    errors.append((uuid, e))
                return None

        with (
            concurrent.futures.ThreadPoolExecutor(
                max_workers=self.parallel_max_workers
            ) as executor,
            tqdm(
                total=len(uuids), desc="Serializing work items", unit="item"
            ) as progress_bar,
        ):
            futures = [
                executor.submit(_serialize_single_safely, uuid)
                for uuid in uuids
            ]
            for future in concurrent.futures.as_completed(futures):
                if work_item := future.result():
                    all_work_items.append(work_item)
                progress_bar.update(1)

        if errors:
            self.error_collector.add_serialization_errors(errors)
            logger.warning("Failed to serialize %d work items", len(errors))
            failure_rate = len(errors) / len(uuids)
            logger.warning(
                "Serialization failure rate: %.1f%%", failure_rate * 100
            )

        logger.info(
            "Completed parallel serialization of %d work items!",
            len(all_work_items),
        )
        return all_work_items
