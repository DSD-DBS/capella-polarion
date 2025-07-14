# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0

from unittest import mock

import capellambse
import pytest

from capella2polarion.connectors import (
    polarion_worker,
    polarion_worker_parallel,
)
from capella2polarion.data_model import work_items
from capella2polarion.elements import converter_config, data_session


def test_polarion_worker_non_delete_mode():
    with mock.patch.object(
        polarion_worker.CapellaPolarionWorker, "check_client"
    ):
        worker = polarion_worker.CapellaPolarionWorker(
            polarion_worker.PolarionWorkerParams(
                project_id="TEST",
                url="http://127.0.0.1",
                pat="PrivateAccessToken",
                delete_work_items=False,
            )
        )
    assert worker.project_client.work_items.delete_status == "deleted"


def test_polarion_worker_delete_mode():
    with mock.patch.object(
        polarion_worker.CapellaPolarionWorker, "check_client"
    ):
        worker = polarion_worker.CapellaPolarionWorker(
            polarion_worker.PolarionWorkerParams(
                project_id="TEST",
                url="http://127.0.0.1",
                pat="PrivateAccessToken",
                delete_work_items=True,
            )
        )
    assert worker.project_client.work_items.delete_status is None


def test_polarion_worker_reuse_deleted_work_item(
    model: capellambse.MelodyModel,
    empty_polarion_worker: polarion_worker.CapellaPolarionWorker,
):
    new_work_item = work_items.CapellaWorkItem(
        "ID", title="Test", status="open", uuid_capella="123", type="test"
    )
    old_work_item = work_items.CapellaWorkItem(
        "ID",
        status="deleted",
        type="test",
        uuid_capella="123",
        checksum=new_work_item.calculate_checksum(),
    )
    empty_polarion_worker.polarion_data_repo.update_work_items([old_work_item])
    empty_polarion_worker.project_client.work_items.get.return_value = (
        old_work_item
    )
    empty_polarion_worker.project_client.work_items.delete_status = "deleted"
    empty_polarion_worker.project_client.work_items.attachments.get_all.return_value = []

    empty_polarion_worker.compare_and_update_work_items(
        {
            "123": data_session.ConverterData(
                "la",
                converter_config.CapellaTypeConfig("test"),
                model.la.extensions.create("FakeModelObject", uuid="123"),
                new_work_item,
            )
        }
    )

    assert (
        empty_polarion_worker.project_client.work_items.update.call_count == 1
    )


def test_parallel_worker_sequential_processing():
    params = polarion_worker.PolarionWorkerParams(
        project_id="TEST",
        url="http://127.0.0.1",
        pat="PrivateAccessToken",
        delete_work_items=False,
    )

    with mock.patch.object(
        polarion_worker_parallel.ParallelCapellaPolarionWorker, "check_client"
    ):
        worker = polarion_worker_parallel.ParallelCapellaPolarionWorker(
            params,
            parallel_threshold=10,
        )

        with mock.patch.object(
            worker, "_compare_and_update_work_items_sequential"
        ) as mock_sequential:
            session = {"1": mock.MagicMock(), "2": mock.MagicMock()}
            for key, data in session.items():
                data.work_item = mock.MagicMock()
                worker.polarion_data_repo.update_work_items(
                    [
                        work_items.CapellaWorkItem(
                            id=key, uuid_capella=key, title="Test", type="test"
                        )
                    ]
                )

            worker.compare_and_update_work_items(session)

            mock_sequential.assert_called_once()


def test_parallel_worker_parallel_processing():
    params = polarion_worker.PolarionWorkerParams(
        project_id="TEST",
        url="http://127.0.0.1",
        pat="PrivateAccessToken",
        delete_work_items=False,
    )

    with mock.patch.object(
        polarion_worker_parallel.ParallelCapellaPolarionWorker, "check_client"
    ):
        worker = polarion_worker_parallel.ParallelCapellaPolarionWorker(
            params,
            parallel_threshold=3,  # Low threshold to enable parallel
            enable_parallel_updates=True,
            enable_batched_operations=False,
        )

        # Mock the parallel method
        with mock.patch.object(
            worker, "_compare_and_update_work_items_parallel"
        ) as mock_parallel:
            # Create a larger converter session (above threshold)
            session = {}
            for i in range(5):  # Above threshold of 3
                key = str(i)
                session[key] = mock.MagicMock()
                session[key].work_item = mock.MagicMock()
                worker.polarion_data_repo.update_work_items(
                    [
                        work_items.CapellaWorkItem(
                            id=key, uuid_capella=key, title="Test", type="test"
                        )
                    ]
                )

            worker.compare_and_update_work_items(session)

            # Should use parallel processing due to high item count
            mock_parallel.assert_called_once()


def test_parallel_worker_batched_processing():
    params = polarion_worker.PolarionWorkerParams(
        project_id="TEST",
        url="http://127.0.0.1",
        pat="PrivateAccessToken",
        delete_work_items=False,
    )

    with mock.patch.object(
        polarion_worker_parallel.ParallelCapellaPolarionWorker, "check_client"
    ):
        worker = polarion_worker_parallel.ParallelCapellaPolarionWorker(
            params,
            parallel_threshold=3,  # Low threshold
            enable_parallel_updates=True,
            enable_batched_operations=True,  # Enable batching
        )

        # Mock the batched method
        with mock.patch.object(
            worker, "_compare_and_update_work_items_batched"
        ) as mock_batched:
            # Create a larger converter session (above threshold)
            session = {}
            for i in range(5):  # Above threshold of 3
                key = str(i)
                session[key] = mock.MagicMock()
                session[key].work_item = mock.MagicMock()
                worker.polarion_data_repo.update_work_items(
                    [
                        work_items.CapellaWorkItem(
                            id=key, uuid_capella=key, title="Test", type="test"
                        )
                    ]
                )

            worker.compare_and_update_work_items(session)

            # Should use batched processing when enabled
            mock_batched.assert_called_once()


def test_parallel_worker_needs_work_item_update():
    params = polarion_worker.PolarionWorkerParams(
        project_id="TEST",
        url="http://127.0.0.1",
        pat="PrivateAccessToken",
        delete_work_items=False,
    )

    with mock.patch.object(
        polarion_worker_parallel.ParallelCapellaPolarionWorker, "check_client"
    ):
        worker = polarion_worker_parallel.ParallelCapellaPolarionWorker(params)

        # Create test work items
        old_work_item = work_items.CapellaWorkItem(
            id="TEST-1", uuid_capella="uuid1", title="Old Title", type="test"
        )
        new_work_item = work_items.CapellaWorkItem(
            id="TEST-1", uuid_capella="uuid1", title="New Title", type="test"
        )

        # Test that update is needed when items differ
        assert (
            worker.needs_work_item_update(new_work_item, old_work_item) is True
        )

        # Test that update is not needed when items are identical
        identical_work_item = work_items.CapellaWorkItem(
            id="TEST-1", uuid_capella="uuid1", title="Old Title", type="test"
        )
        identical_work_item.checksum = old_work_item.calculate_checksum()
        assert (
            worker.needs_work_item_update(identical_work_item, old_work_item)
            is False
        )


@pytest.mark.parametrize(
    ("error_count", "total_items", "should_raise_error"),
    [(1, 12, False), (2, 10, True)],
)
def test_parallel_worker_error_handling(
    error_count: int, total_items: int, should_raise_error: bool
):
    params = polarion_worker.PolarionWorkerParams(
        project_id="TEST",
        url="http://127.0.0.1",
        pat="PrivateAccessToken",
        delete_work_items=False,
    )

    with mock.patch.object(
        polarion_worker_parallel.ParallelCapellaPolarionWorker, "check_client"
    ):
        worker = polarion_worker_parallel.ParallelCapellaPolarionWorker(
            params, parallel_threshold=1, max_workers=2
        )

        original_method = worker.compare_and_update_work_item

        def side_effect(data):
            if data.work_item.uuid_capella.startswith("error_item"):
                raise RuntimeError("Test error")
            return original_method(data)

        session = {}
        success_count = total_items - error_count
        for i in range(success_count):
            uuid = f"success_item_{i}"
            session[uuid] = mock.MagicMock()
            session[uuid].work_item = work_items.CapellaWorkItem(
                id=f"TEST-{i}",
                uuid_capella=uuid,
                title="Test",
                type="test",
            )
            worker.polarion_data_repo.update_work_items(
                [session[uuid].work_item]
            )

        for i in range(error_count):
            uuid = f"error_item_{i}"
            session[uuid] = mock.MagicMock()
            session[uuid].work_item = work_items.CapellaWorkItem(
                id=f"TEST-{success_count + i}",
                uuid_capella=uuid,
                title="Test",
                type="test",
            )
            worker.polarion_data_repo.update_work_items(
                [session[uuid].work_item]
            )

        with mock.patch.object(
            worker, "compare_and_update_work_item", side_effect=side_effect
        ):
            if should_raise_error:
                with pytest.raises(
                    RuntimeError, match="Too many work item update failures"
                ):
                    worker.compare_and_update_work_items(session)
            else:
                worker.compare_and_update_work_items(session)

            assert (
                worker.compare_and_update_work_item.call_count == total_items
            )
