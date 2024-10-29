# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
import typing as t
from unittest import mock

import polarion_rest_api_client as polarion_api
import pytest
from click import testing

import capella2polarion.__main__ as main
from capella2polarion.connectors import polarion_worker
from capella2polarion.converters import model_converter

# pylint: disable-next=relative-beyond-top-level, useless-suppression
from .conftest import (  # type: ignore[import]
    TEST_COMBINED_DOCUMENT_CONFIG,
    TEST_MODEL,
    TEST_MODEL_ELEMENTS_CONFIG,
)


class CLIMocks(t.NamedTuple):
    """Mocks for CLI functions."""

    get_polarion_wi_map: mock.MagicMock
    generate_work_items: mock.MagicMock
    delete_work_items: mock.MagicMock
    patch_work_items: mock.MagicMock
    post_work_items: mock.MagicMock
    get_document: mock.MagicMock
    create_documents: mock.MagicMock
    update_documents: mock.MagicMock


@pytest.fixture(scope="function")
def cli_mocks(monkeypatch: pytest.MonkeyPatch) -> CLIMocks:
    mock_api_client = mock.MagicMock(spec=polarion_api.PolarionClient)
    monkeypatch.setattr(polarion_api, "PolarionClient", mock_api_client)
    mock_project_client = mock.MagicMock(spec=polarion_api.ProjectClient)
    monkeypatch.setattr(polarion_api, "ProjectClient", mock_project_client)
    mock_get_polarion_wi_map = mock.MagicMock()
    monkeypatch.setattr(
        polarion_worker.CapellaPolarionWorker,
        "load_polarion_work_item_map",
        mock_get_polarion_wi_map,
    )
    mock_generate_work_items = mock.MagicMock()
    monkeypatch.setattr(
        model_converter.ModelConverter,
        "generate_work_items",
        mock_generate_work_items,
    )
    mock_delete_work_items = mock.MagicMock()
    monkeypatch.setattr(
        polarion_worker.CapellaPolarionWorker,
        "delete_orphaned_work_items",
        mock_delete_work_items,
    )
    mock_post_work_items = mock.MagicMock()
    monkeypatch.setattr(
        polarion_worker.CapellaPolarionWorker,
        "create_missing_work_items",
        mock_post_work_items,
    )
    mock_patch_work_items = mock.MagicMock()
    monkeypatch.setattr(
        polarion_worker.CapellaPolarionWorker,
        "compare_and_update_work_items",
        mock_patch_work_items,
    )
    mock_get_document = mock.MagicMock()
    mock_get_document.side_effect = lambda folder, name, project_id: (
        polarion_api.Document(
            module_folder=folder,
            module_name=name,
            home_page_content=polarion_api.TextContent(
                "text/html",
                '<h1 id="polarion_wiki macro name=module-workitem;'
                'params=id=TEST-123"></h1>',
            ),
        )
        if name == "id1236"
        else None
    )
    monkeypatch.setattr(
        polarion_worker.CapellaPolarionWorker,
        "get_document",
        mock_get_document,
    )
    mock_create_documents = mock.MagicMock()
    monkeypatch.setattr(
        polarion_worker.CapellaPolarionWorker,
        "create_documents",
        mock_create_documents,
    )
    mock_update_documents = mock.MagicMock()
    monkeypatch.setattr(
        polarion_worker.CapellaPolarionWorker,
        "update_documents",
        mock_update_documents,
    )
    return CLIMocks(
        get_polarion_wi_map=mock_get_polarion_wi_map,
        generate_work_items=mock_generate_work_items,
        delete_work_items=mock_delete_work_items,
        patch_work_items=mock_post_work_items,
        post_work_items=mock_post_work_items,
        get_document=mock_get_document,
        create_documents=mock_create_documents,
        update_documents=mock_update_documents,
    )


# pylint: disable=redefined-outer-name
def test_migrate_model_elements(cli_mocks: CLIMocks):
    command: list[str] = [
        "--polarion-project-id",
        "{project-id}",
        "--polarion-url",
        "https://www.capella2polarion.invalid",
        "--polarion-pat",
        "PrivateAcessToken",
        "--polarion-delete-work-items",
        "--capella-model",
        json.dumps(TEST_MODEL),
        "synchronize",
        "--synchronize-config",
        str(TEST_MODEL_ELEMENTS_CONFIG),
        "--grouped-links-custom-fields",
    ]

    result = testing.CliRunner().invoke(main.cli, command, terminal_width=60)

    assert result.exit_code == 0
    assert cli_mocks.get_polarion_wi_map.call_count == 1
    assert cli_mocks.generate_work_items.call_count == 1
    assert cli_mocks.generate_work_items.call_args_list[0][1] == {
        "generate_links": True,
        "generate_attachments": True,
        "generate_grouped_links_custom_fields": True,
    }
    assert cli_mocks.delete_work_items.call_count == 1
    assert cli_mocks.patch_work_items.call_count == 1
    assert cli_mocks.post_work_items.call_count == 1


def test_render_documents(cli_mocks: CLIMocks):
    command: list[str] = [
        "--polarion-project-id",
        "{project-id}",
        "--polarion-url",
        "https://www.capella2polarion.invalid",
        "--polarion-pat",
        "PrivateAcessToken",
        "--polarion-delete-work-items",
        "--capella-model",
        json.dumps(TEST_MODEL),
        "render-documents",
        "--document-rendering-config",
        str(TEST_COMBINED_DOCUMENT_CONFIG),
    ]

    result = testing.CliRunner().invoke(main.cli, command, terminal_width=60)

    assert result.exit_code == 0
    assert cli_mocks.get_polarion_wi_map.call_count == 1
    assert cli_mocks.get_document.call_count == 8
    assert [
        call.args[2] for call in cli_mocks.get_document.call_args_list
    ] == [
        None,
        None,
        None,
        "TestProject",
        None,
        None,
        None,
        "TestProject",
    ]

    assert cli_mocks.create_documents.call_count == 2
    assert len(cli_mocks.create_documents.call_args_list[0].args[0]) == 1
    assert len(cli_mocks.create_documents.call_args_list[1].args[0]) == 1
    assert cli_mocks.create_documents.call_args_list[0].args[1] is None
    assert (
        cli_mocks.create_documents.call_args_list[1].args[1] == "TestProject"
    )

    assert cli_mocks.update_documents.call_count == 2
    assert len(cli_mocks.update_documents.call_args_list[0].args[0]) == 1
    assert len(cli_mocks.update_documents.call_args_list[1].args[0]) == 0
    assert cli_mocks.update_documents.call_args_list[0].args[1] is None
    assert (
        cli_mocks.update_documents.call_args_list[1].args[1] == "TestProject"
    )
