# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0

from unittest import mock

from capella2polarion.connectors import polarion_worker


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
