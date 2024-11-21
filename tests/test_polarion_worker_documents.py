# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0
from unittest import mock

import polarion_rest_api_client as polarion_api

from capella2polarion import data_model
from capella2polarion.connectors import polarion_worker
from capella2polarion.converters import text_work_item_provider

from .conftest import DOCUMENT_TEMPLATES, DOCUMENT_TEXT_WORK_ITEMS


def test_update_document(
    empty_polarion_worker: polarion_worker.CapellaPolarionWorker,
):
    path = DOCUMENT_TEMPLATES / DOCUMENT_TEXT_WORK_ITEMS
    document = polarion_api.Document(
        module_folder="_default",
        module_name="TEST-DOC",
        rendering_layouts=[],
        home_page_content=polarion_api.TextContent(
            type="text/html",
            value=path.read_text("utf-8"),
        ),
    )
    document_data = data_model.DocumentData(
        document,
        [],
        text_work_item_provider.TextWorkItemProvider(
            "MyField",
            "MyType",
            [
                polarion_api.WorkItem(
                    id="EXISTING", additional_attributes={"MyField": "id1"}
                ),
            ],
        ),
    )
    document_data.text_work_item_provider.generate_text_work_items(
        document.home_page_content.value
    )
    client = empty_polarion_worker.project_client

    empty_polarion_worker.update_documents([document_data])

    assert document.home_page_content.value.endswith(
        '<div id="polarion_wiki macro name=module-workitem;'
        'params=id=EXISTING|layout=0|external=true"></div>\n'
        '<div id="polarion_wiki macro name=module-workitem;'
        'params=id=AUTO-0|layout=0|external=true"></div>'
    )
    assert client.documents.update.call_count == 1
    assert client.documents.update.call_args.args[0] == [document]
    assert client.work_items.create.call_count == 1
    assert len(client.work_items.create.call_args.args[0]) == 1
    assert client.work_items.update.call_count == 2
    assert len(client.work_items.update.call_args_list[0].args[0]) == 1
    assert len(client.work_items.update.call_args_list[1].args[0]) == 0


def test_create_document(
    empty_polarion_worker: polarion_worker.CapellaPolarionWorker,
):
    path = DOCUMENT_TEMPLATES / DOCUMENT_TEXT_WORK_ITEMS
    document = polarion_api.Document(
        module_folder="_default",
        module_name="TEST-DOC",
        rendering_layouts=[],
        home_page_content=polarion_api.TextContent(
            type="text/html",
            value=path.read_text("utf-8"),
        ),
    )
    document_data = data_model.DocumentData(
        document,
        [],
        text_work_item_provider.TextWorkItemProvider(
            "MyField",
            "MyType",
        ),
    )
    document_data.text_work_item_provider.generate_text_work_items(
        document.home_page_content.value
    )
    client = empty_polarion_worker.project_client

    empty_polarion_worker.update_documents([document_data])

    assert document.home_page_content.value.endswith(
        '<div id="polarion_wiki macro name=module-workitem;'
        'params=id=AUTO-0|layout=0|external=true"></div>\n'
        '<div id="polarion_wiki macro name=module-workitem;'
        'params=id=AUTO-1|layout=0|external=true"></div>'
    )
    assert client.documents.update.call_count == 1
    assert client.documents.update.call_args.args[0] == [document]
    assert client.work_items.create.call_count == 1
    assert len(client.work_items.create.call_args.args[0]) == 2
    assert client.work_items.update.call_count == 2
    assert len(client.work_items.update.call_args_list[0].args[0]) == 0
    assert len(client.work_items.update.call_args_list[1].args[0]) == 0


def test_use_correct_client(
    empty_polarion_worker: polarion_worker.CapellaPolarionWorker,
):
    empty_polarion_worker.project_client = mock.MagicMock()
    document = polarion_api.Document(
        module_folder="_default",
        module_name="TEST-DOC-A",
        rendering_layouts=[],
        home_page_content=polarion_api.TextContent(
            type="text/html",
            value="",
        ),
    )

    document_data = data_model.DocumentData(
        document,
        [],
        text_work_item_provider.TextWorkItemProvider(),
    )

    empty_polarion_worker.create_documents([document_data], "OtherProject")
    empty_polarion_worker.update_documents([document_data], "OtherProject")

    assert len(empty_polarion_worker.project_client.method_calls) == 0
    assert len(empty_polarion_worker._additional_clients) == 1
    assert (
        client := empty_polarion_worker._additional_clients.get("OtherProject")
    )
    assert client.documents.update.call_count == 1
    assert client.documents.create.call_count == 1
    assert client.work_items.update.call_count == 1
