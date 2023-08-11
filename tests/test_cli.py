# Copyright DB Netz AG and contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import collections.abc as cabc
import os
import pathlib
import typing as t
from unittest import mock

import polarion_rest_api_client as polarion_api
import pytest
from click import testing

import capella2polarion.__main__ as main
from capella2polarion import elements

# pylint: disable-next=relative-beyond-top-level, useless-suppression
from .conftest import (  # type: ignore[import]
    TEST_DIAGRAM_CACHE,
    TEST_HOST,
    TEST_MODEL,
    TEST_MODEL_ELEMENTS_CONFIG,
)

ELEMENTS_IDX_PATH = pathlib.Path("elements_index.yaml")


def prepare_cli_test(
    monkeypatch: pytest.MonkeyPatch, return_value: t.Any | cabc.Iterable[t.Any]
) -> mock.MagicMock:
    os.environ["POLARION_HOST"] = TEST_HOST
    os.environ["POLARION_PAT"] = "1234"
    mock_api = mock.MagicMock(spec=polarion_api.OpenAPIPolarionProjectClient)
    monkeypatch.setattr(polarion_api, "OpenAPIPolarionProjectClient", mock_api)
    mock_get_polarion_wi_map = mock.MagicMock()
    monkeypatch.setattr(main, "get_polarion_wi_map", mock_get_polarion_wi_map)
    if isinstance(return_value, cabc.Iterable) and not isinstance(
        return_value, (str, dict)
    ):
        id_map_attr = "side_effect"
    else:
        id_map_attr = "return_value"

    setattr(mock_get_polarion_wi_map, id_map_attr, return_value)
    return mock_get_polarion_wi_map


def test_migrate_diagrams(monkeypatch: pytest.MonkeyPatch):
    mock_get_polarion_wi_map = prepare_cli_test(
        monkeypatch,
        {
            "uuid1": polarion_api.WorkItem("project/W-1"),
            "uuid2": polarion_api.WorkItem("project/W-2"),
        },
    )
    mock_delete_work_items = mock.MagicMock()
    monkeypatch.setattr(elements, "delete_work_items", mock_delete_work_items)
    mock_update_diagrams = mock.MagicMock()
    monkeypatch.setattr(
        elements.diagram, "update_diagrams", mock_update_diagrams
    )
    mock_create_diagrams = mock.MagicMock()
    monkeypatch.setattr(
        elements.diagram, "create_diagrams", mock_create_diagrams
    )
    command = ["--project-id=project_id", "diagrams", str(TEST_DIAGRAM_CACHE)]

    result = testing.CliRunner().invoke(main.cli, command)

    assert result.exit_code == 0
    assert mock_get_polarion_wi_map.call_count == 1
    assert mock_delete_work_items.call_count == 1
    assert mock_update_diagrams.call_count == 1
    assert mock_create_diagrams.call_count == 1


def test_migrate_model_elements(monkeypatch: pytest.MonkeyPatch):
    mock_get_polarion_wi_map = prepare_cli_test(
        monkeypatch,
        (
            {
                "5b1f761c-3fd3-4f26-bbc5-1b06a6f7b434": polarion_api.WorkItem(
                    "project/W-0"
                ),
                "uuid1": polarion_api.WorkItem("project/W-1"),
                "uuid2": polarion_api.WorkItem("project/W-2"),
            },
            {
                "uuid2": polarion_api.WorkItem("project/W-2"),
                "uuid3": polarion_api.WorkItem("project/W-3"),
            },
            {},
        ),
    )
    mock_delete_work_items = mock.MagicMock()
    monkeypatch.setattr(elements, "delete_work_items", mock_delete_work_items)
    mock_update_work_items = mock.MagicMock()
    monkeypatch.setattr(
        elements.element, "update_work_items", mock_update_work_items
    )
    mock_create_work_items = mock.MagicMock()
    monkeypatch.setattr(
        elements.element, "create_work_items", mock_create_work_items
    )
    mock_update_links = mock.MagicMock()
    monkeypatch.setattr(elements.element, "update_links", mock_update_links)

    command = [
        "--project-id=project_id",
        "model-elements",
        str(TEST_MODEL),
        str(TEST_MODEL_ELEMENTS_CONFIG),
    ]

    result = testing.CliRunner().invoke(main.cli, command)

    assert result.exit_code == 0
    assert mock_get_polarion_wi_map.call_count == 3
    assert mock_delete_work_items.call_count == 1
    assert mock_update_work_items.call_count == 1
    assert mock_create_work_items.call_count == 1
    assert mock_update_links.call_count == 2
    assert ELEMENTS_IDX_PATH.exists()
