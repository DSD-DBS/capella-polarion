# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
"""Error collection and reporting for capella2polarion."""

import logging
import sys

logger = logging.getLogger(__name__)

ERROR_LOOKUP_LIMIT: int = 5


class ErrorCollector:
    """Collects errors during synchronization for proper exit code handling."""

    def __init__(self) -> None:
        self.work_item_errors: list[tuple[str, Exception]] = []
        self.link_errors: list[tuple[str, Exception]] = []
        self.critical_errors: list[Exception] = []

    def add_work_item_error(self, uuid: str, error: Exception) -> None:
        """Add a work item processing error."""
        self.work_item_errors.append((uuid, error))

    def add_link_error(self, uuid: str, error: Exception) -> None:
        """Add a link processing error."""
        self.link_errors.append((uuid, error))

    def add_link_errors(self, errors: list[tuple[str, Exception]]) -> None:
        """Add multiple link processing errors."""
        self.link_errors.extend(errors)

    def add_critical_error(self, error: Exception) -> None:
        """Add a critical error that should cause immediate failure."""
        self.critical_errors.append(error)

    def has_errors(self) -> bool:
        """Check if any errors were collected."""
        return bool(
            self.work_item_errors or self.link_errors or self.critical_errors
        )

    def get_exit_code(self) -> int:
        """Get appropriate exit code based on collected errors."""
        if self.critical_errors:
            return 2
        if self.work_item_errors or self.link_errors:
            return 1
        return 0

    def report_errors_and_exit(self) -> None:
        """Report error summary and exit with appropriate code."""
        if not self.has_errors():
            logger.info("Synchronization completed successfully")
            return

        total_errors = (
            len(self.work_item_errors)
            + len(self.link_errors)
            + len(self.critical_errors)
        )
        logger.error("Synchronization completed with %d errors:", total_errors)
        if self.work_item_errors:
            logger.error(
                "Work item processing errors: %d",
                len(self.work_item_errors),
            )
            for uuid, error in self.work_item_errors[:ERROR_LOOKUP_LIMIT]:
                logger.error("  - %s: %s", uuid, error)
            if len(self.work_item_errors) > ERROR_LOOKUP_LIMIT:
                logger.error(
                    "  ... and %d more work item errors",
                    len(self.work_item_errors) - ERROR_LOOKUP_LIMIT,
                )

        if self.link_errors:
            logger.error("Link processing errors: %d", len(self.link_errors))
            for uuid, error in self.link_errors[:ERROR_LOOKUP_LIMIT]:
                logger.error("  - %s: %s", uuid, error)
            if len(self.link_errors) > ERROR_LOOKUP_LIMIT:
                logger.error(
                    "  ... and %d more link errors",
                    len(self.link_errors) - ERROR_LOOKUP_LIMIT,
                )

        if self.critical_errors:
            logger.error("Critical errors: %d", len(self.critical_errors))
            for error in self.critical_errors:
                logger.error("  - %s", error)

        exit_code = self.get_exit_code()
        sys.exit(exit_code)
