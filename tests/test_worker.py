# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0

from unittest import mock

import capellambse

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
            max_workers=4,
            enable_parallel_updates=False,
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
            max_workers=4,
            enable_parallel_updates=True,
            enable_batched_operations=False,
        )
        with mock.patch.object(
            worker, "_compare_and_update_work_items_parallel"
        ) as mock_parallel:
            session = {}
            for i in range(5):
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
            max_workers=4,
            enable_parallel_updates=True,
            enable_batched_operations=True,
        )
        with mock.patch.object(
            worker, "_compare_and_update_work_items_batched"
        ) as mock_batched:
            session = {}
            for i in range(5):
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
        worker = polarion_worker_parallel.ParallelCapellaPolarionWorker(
            params, max_workers=4
        )
        old_work_item = work_items.CapellaWorkItem(
            id="TEST-1", uuid_capella="uuid1", title="Old Title", type="test"
        )
        new_work_item = work_items.CapellaWorkItem(
            id="TEST-1", uuid_capella="uuid1", title="New Title", type="test"
        )
        identical_work_item = work_items.CapellaWorkItem(
            id="TEST-1", uuid_capella="uuid1", title="Old Title", type="test"
        )
        identical_work_item.checksum = old_work_item.calculate_checksum()

        assert (
            worker.needs_work_item_update(new_work_item, old_work_item) is True
        )
        assert (
            worker.needs_work_item_update(identical_work_item, old_work_item)
            is False
        )
