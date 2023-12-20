# Copyright DB InfraGO AG and contributors
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import collections.abc as cabc
import os
import pathlib
import typing
from unittest import mock

import polarion_rest_api_client as polarion_api
import pytest
from click import testing

import capella2polarion.__main__ as main
from capella2polarion import elements
from capella2polarion.c2pcli import C2PCli
from capella2polarion.c2polarion import PolarionWorker

# pylint: disable-next=relative-beyond-top-level, useless-suppression
from tests.conftest import (  # type: ignore[import]
    TEST_DIAGRAM_CACHE,
    TEST_HOST,
    TEST_MODEL,
    TEST_MODEL_ELEMENTS_CONFIG,
)


def prepare_cli_test(
    monkeypatch: pytest.MonkeyPatch,
    return_value: typing.Any | cabc.Iterable[typing.Any],
) -> mock.MagicMock:
    os.environ["POLARION_HOST"] = TEST_HOST
    os.environ["POLARION_PAT"] = "1234"
    mock_api = mock.MagicMock(spec=polarion_api.OpenAPIPolarionProjectClient)
    monkeypatch.setattr(polarion_api, "OpenAPIPolarionProjectClient", mock_api)
    # # mock_get_polarion_wi_map = mock.MagicMock()
    # # monkeypatch.setattr(
    # #     elements, "get_polarion_wi_map", mock_get_polarion_wi_map
    # # )
    # if isinstance(return_value, cabc.Iterable) and not isinstance(
    #     return_value, (str, dict)
    # ):
    #     id_map_attr = "side_effect"
    # else:
    #     id_map_attr = "return_value"

    # setattr(mock_get_polarion_wi_map, id_map_attr, return_value)
    # return mock_get_polarion_wi_map
    return mock_api


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
    # mock_delete_work_items = mock.MagicMock()
    # monkeypatch.setattr(elements, "delete_work_items", mock_delete_work_items)
    # mock_post_work_items = mock.MagicMock()
    # monkeypatch.setattr(elements, "post_work_items", mock_post_work_items)
    # mock_patch_work_items = mock.MagicMock()
    # monkeypatch.setattr(elements, "patch_work_items", mock_patch_work_items)

    command = [
        "--polarion-project-id",
        "{project-id}",
        "--polarion-url",
        "https://www.czy.de",
        "--polarion-pat",
        "AlexandersPrivateAcessToken",
        "--polarion-delete-work-items",
        "--capella-diagram-cache-folder-path",
        "./tests/data/diagram_cache",
        "--capella-model",
        "./tests/data/model/Melody Model Test.aird",
        "--synchronize-config",
        "./tests/data/model_elements/config.yaml",
        "synchronize"
        # ,str(TEST_MODEL),
        # ,str(TEST_DIAGRAM_CACHE),
        # ,str(TEST_MODEL_ELEMENTS_CONFIG),
    ]

    mock_polarionworker_deleteworkitem = mock.MagicMock()
    mock.patch.object(
        PolarionWorker.setup_client,
        mock_polarionworker_deleteworkitem,
    )
    mock.patch.object(
        PolarionWorker.delete_work_items, mock_polarionworker_deleteworkitem
    )

    # mock_c2pcli_setuplogger = mock.MagicMock()
    mock.patch.object(
        C2PCli.load_synchronize_config, mock_polarionworker_deleteworkitem
    )

    result = testing.CliRunner().invoke(main.cli, command, terminal_width=60)

    # TODO Dieser Test funktioniert nur wenn in der __main__.py in
    # der Zeile 113 simulation auf True gesetellt wird
    # oder halt polarion auch vorhanden ist.
    # polarion_worker.simulation = True
    assert result.exit_code == 0

    # assert mock_c2pcli_setuplogger.call_count == 1
    # assert mock_get_polarion_wi_map.call_count == 1
    # assert mock_delete_work_items.call_count == 1
    # assert mock_patch_work_items.call_count == 1
    # assert mock_post_work_items.call_count == 1
