# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0

import polarion_rest_api_client as polarion_api

from capella2polarion import data_models
from capella2polarion.connectors import polarion_worker
from capella2polarion.converters import text_work_item_provider

from .conftest import DOCUMENT_TEMPLATES, DOCUMENT_TEXT_WORK_ITEMS


def _set_work_item_id(work_items: list[polarion_api.WorkItem]):
    for index, work_item in enumerate(work_items):
        work_item.id = f"id{index}"


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
    document_data = data_models.DocumentData(
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
    empty_polarion_worker.project_client.work_items.create.side_effect = (
        _set_work_item_id
    )

    empty_polarion_worker.update_documents([document_data])

    assert document.home_page_content.value.endswith(
        '<div id="polarion_wiki macro name=module-workitem;'
        'params=id=EXISTING|layout=0|external=true"></div>\n'
        '<div id="polarion_wiki macro name=module-workitem;'
        'params=id=id0|layout=0|external=true"></div>'
    )
    assert (
        empty_polarion_worker.project_client.documents.update.call_count == 1
    )
    assert (
        empty_polarion_worker.project_client.documents.update.call_args.args[0]
        == [document]
    )
    assert (
        empty_polarion_worker.project_client.work_items.create.call_count == 1
    )
    assert (
        len(
            empty_polarion_worker.project_client.work_items.create.call_args.args[
                0
            ]
        )
        == 1
    )
    assert (
        empty_polarion_worker.project_client.work_items.update.call_count == 2
    )
    assert (
        len(
            empty_polarion_worker.project_client.work_items.update.call_args_list[
                0
            ].args[
                0
            ]
        )
        == 1
    )
    assert (
        len(
            empty_polarion_worker.project_client.work_items.update.call_args_list[
                1
            ].args[
                0
            ]
        )
        == 0
    )


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
    document_data = data_models.DocumentData(
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
    empty_polarion_worker.project_client.work_items.create.side_effect = (
        _set_work_item_id
    )

    empty_polarion_worker.update_documents([document_data])

    assert document.home_page_content.value.endswith(
        '<div id="polarion_wiki macro name=module-workitem;'
        'params=id=id0|layout=0|external=true"></div>\n'
        '<div id="polarion_wiki macro name=module-workitem;'
        'params=id=id1|layout=0|external=true"></div>'
    )
    assert (
        empty_polarion_worker.project_client.documents.update.call_count == 1
    )
    assert (
        empty_polarion_worker.project_client.documents.update.call_args.args[0]
        == [document]
    )
    assert (
        empty_polarion_worker.project_client.work_items.create.call_count == 1
    )
    assert (
        len(
            empty_polarion_worker.project_client.work_items.create.call_args.args[
                0
            ]
        )
        == 2
    )
    assert (
        empty_polarion_worker.project_client.work_items.update.call_count == 2
    )
    assert (
        len(
            empty_polarion_worker.project_client.work_items.update.call_args_list[
                0
            ].args[
                0
            ]
        )
        == 0
    )
    assert (
        len(
            empty_polarion_worker.project_client.work_items.update.call_args_list[
                1
            ].args[
                0
            ]
        )
        == 0
    )
