# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0

from unittest import mock

from capella2polarion.connectors import polarion_worker
from capella2polarion.converters import converter_config, data_session
from capella2polarion.data_model import work_items

# pylint: disable-next=relative-beyond-top-level, useless-suppression
from .conftest import FakeModelObject  # type: ignore[import]


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
    empty_polarion_worker.compare_and_update_work_items(
        {
            "123": data_session.ConverterData(
                "la",
                converter_config.CapellaTypeConfig("test"),
                FakeModelObject("123"),
                new_work_item,
            )
        }
    )

    assert (
        empty_polarion_worker.project_client.work_items.update.call_count == 1
    )
